<template>
  <!-- 左侧：选知识库并新建会话；右侧：消息列表和输入框。发送走 SSE 流式接口。 -->
  <el-container class="chat-wrap">
    <el-aside width="280px" class="aside">
      <el-form label-position="top" style="padding: 0 8px 12px">
        <el-form-item label="知识库">
          <el-select
            ref="kbSelectRef"
            v-model="createForm.knowledge_base_ids"
            multiple
            placeholder="选择知识库"
            style="width: 100%"
            @change="closeKbDropdown"
          >
            <el-option v-for="k in kbs" :key="k.id" :label="k.name" :value="k.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="模式">
          <el-select v-model="createForm.mode" style="width: 100%">
            <el-option label="RAG" value="rag" />
            <el-option label="Agent（LangGraph）" value="agent" />
          </el-select>
        </el-form-item>
        <el-button type="primary" style="width: 100%" @click="createConv">新建会话</el-button>
      </el-form>
      <div class="conv-list">
        <div
          v-for="c in convs"
          :key="c.id"
          class="conv-item"
          :class="{ active: c.id === currentId, 'menu-open': openMenuId === c.id }"
          @click="router.push(`/chat/${c.id}`)"
        >
          <span class="conv-main">
            <span v-if="c.is_pinned" class="pin-dot" title="已置顶">📌</span>
            <span class="conv-title">{{ c.title }}</span>
            <el-tag v-if="auth.isAdmin" size="small" :type="c.owner_kind === '管理者' ? 'warning' : 'info'">
              {{ c.owner_kind }}
            </el-tag>
            <el-tag size="small" type="info">{{ c.mode }}</el-tag>
          </span>
          <el-dropdown
            trigger="hover"
            :show-timeout="0"
            :hide-timeout="200"
            @command="(cmd: string) => onConvCommand(cmd, c)"
            @visible-change="(v: boolean) => (openMenuId = v ? c.id : '')"
            @click.stop
          >
            <button class="more-btn" type="button" @click.stop title="更多">···</button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item :command="c.is_pinned ? 'unpin' : 'pin'">
                  {{ c.is_pinned ? "取消置顶" : "置顶" }}
                </el-dropdown-item>
                <el-dropdown-item command="rename">重命名</el-dropdown-item>
                <el-dropdown-item command="delete" divided>
                  <span class="danger-item">删除</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </el-aside>
    <el-container class="chat-right">
      <el-main class="chat-main">
        <div ref="msgPane" class="msg-pane">
        <el-empty v-if="!currentId" description="请选择或新建会话" />
        <template v-else>
          <p class="hint">当前模式：{{ currentConv?.mode || "-" }}</p>
          <div v-if="!messages.length" class="guides">
            <p class="guide-title">你可以试着问</p>
            <p v-if="guideLoading" class="guide-empty">正在根据知识库生成引导问题…</p>
            <button
              v-for="q in suggestions"
              :key="q"
              type="button"
              class="guide-card"
              :disabled="sending"
              @click="sendGuide(q)"
            >
              {{ q }}
            </button>
            <p v-if="!guideLoading && !suggestions.length" class="guide-empty">
              当前知识库还没有可检索内容，上传并解析完成后再来看看。
            </p>
          </div>
          <ChatMessage
            v-for="m in messages"
            :key="m.id"
            :role="m.role"
            :content="m.content"
            :citations="m.citations"
            :tools="m.tools"
            :thinking="sending && m.role === 'assistant' && !m.content"
            :streaming="Boolean(m.streaming)"
          />
        </template>
        </div>
      </el-main>
      <el-footer height="80px" class="composer">
        <el-input v-model="question" placeholder="输入问题，Enter 发送" :disabled="!currentId" @keyup.enter="send" />
        <el-button type="primary" :disabled="!currentId" :loading="sending" @click="send">发送</el-button>
      </el-footer>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
// Chat.vue：loadKbs/loadConvs 拉列表；createConv 必须先选知识库；send 用 fetch 读 SSE。
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";
import ChatMessage from "../components/ChatMessage.vue";
import { notifyLimit } from "../utils/notifyLimit";
import { useAuthStore } from "../stores/auth";

interface Citation {
  chunk_id: string;
  filename: string;
  page_number: number | null;
  heading: string | null;
  score: number;
  snippet: string;
}
interface ToolEvt {
  name: string;
  status: string;
  content: string;
}
interface Msg {
  id: string;
  role: string;
  content: string;
  citations: Citation[];
  tools: ToolEvt[];
  streaming?: boolean;
}
interface Conv {
  id: string;
  title: string;
  mode: string;
  is_pinned?: boolean;
  owner_kind?: string;
  owner_username?: string;
}
interface KB {
  id: string;
  name: string;
}

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const convs = ref<Conv[]>([]);
const kbs = ref<KB[]>([]);
const messages = ref<Msg[]>([]);
const question = ref("");
const sending = ref(false);
const openMenuId = ref("");
const suggestions = ref<string[]>([]);
const guideLoading = ref(false);
const createForm = reactive({ knowledge_base_ids: [] as string[], mode: "rag", title: "新对话" });
const kbSelectRef = ref<{ blur: () => void } | null>(null);

function closeKbDropdown() {
  // 选中一项后收起下拉，避免挡着新建会话按钮
  nextTick(() => kbSelectRef.value?.blur());
}

const currentId = computed(() => (route.params.conversationId as string) || "");
const currentConv = computed(() => convs.value.find((c) => c.id === currentId.value));
const msgPane = ref<HTMLElement | null>(null);

function scrollToLatest() {
  // 把右侧对话滚到最底部，看到最新一条
  nextTick(() => {
    const el = msgPane.value;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  });
}

async function loadConvs() {
  // 刷新左侧会话列表
  const { data } = await http.get("/conversations", { params: { page_size: 100 } });
  convs.value = data.data.items || [];
}
async function loadKbs() {
  // 新建会话时要选的知识库下拉框
  const { data } = await http.get("/knowledge-bases");
  kbs.value = data.data || [];
}
async function loadMessages(id: string) {
  // 打开某个会话时拉历史消息
  const { data } = await http.get(`/conversations/${id}`);
  messages.value = (data.data.messages || []).map((m: Msg) => ({
    ...m,
    tools: m.tools || [],
    citations: m.citations || [],
  }));
}

async function loadSuggestions(id: string) {
  // 空会话才拉引导问题，避免干扰已有聊天
  suggestions.value = [];
  guideLoading.value = true;
  try {
    const { data } = await http.get(`/conversations/${id}/suggested-questions`);
    suggestions.value = data.data.questions || [];
  } catch {
    suggestions.value = [];
  } finally {
    guideLoading.value = false;
  }
}

async function createConv() {
  // 必须先勾选知识库，否则检索没有范围
  if (convs.value.length >= 10) {
    notifyLimit("新对话最多 10 个，请先删除后再创建");
    return;
  }
  if (!createForm.knowledge_base_ids.length) {
    ElMessage.warning("请至少选择一个知识库");
    return;
  }
  const { data } = await http.post("/conversations", createForm);
  createForm.knowledge_base_ids = [];
  await loadConvs();
  router.push(`/chat/${data.data.id}`);
}

async function onConvCommand(cmd: string, conv: Conv) {
  // 三点菜单：置顶 / 重命名 / 删除。点取消会抛异常，这里吞掉。
  try {
    if (cmd === "pin" || cmd === "unpin") {
      await http.patch(`/conversations/${conv.id}`, { is_pinned: cmd === "pin" });
      ElMessage.success(cmd === "pin" ? "已置顶" : "已取消置顶");
      await loadConvs();
      return;
    }
    if (cmd === "rename") {
      const { value } = await ElMessageBox.prompt("请输入会话名称", "重命名", {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        inputValue: conv.title,
        inputPattern: /\S+/,
        inputErrorMessage: "名称不能为空",
      });
      await http.patch(`/conversations/${conv.id}`, { title: String(value).trim() });
      ElMessage.success("已重命名");
      await loadConvs();
      return;
    }
    if (cmd === "delete") {
      await ElMessageBox.confirm(`删除后，「${conv.title}」中的消息将不可恢复。`, "删除对话", {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        confirmButtonClass: "el-button--danger",
      });
      await http.delete(`/conversations/${conv.id}`);
      ElMessage.success("已删除");
      if (currentId.value === conv.id) {
        router.push("/chat");
      }
      await loadConvs();
    }
  } catch (err) {
    if (err === "cancel" || err === "close") return;
    throw err;
  }
}

async function sendGuide(q: string) {
  // 点引导问题：填入输入框并直接发送
  question.value = q;
  suggestions.value = [];
  await send();
}

async function send() {
  // 用 fetch 读 SSE：axios 不好处理逐字流
  if (!currentId.value || !question.value.trim()) return;
  sending.value = true;
  const q = question.value.trim();
  question.value = "";
  messages.value.push({ id: "tmp-user", role: "user", content: q, citations: [], tools: [] });
  const assistant: Msg = { id: "stream", role: "assistant", content: "", citations: [], tools: [], streaming: true };
  messages.value.push(assistant);
  scrollToLatest();
  try {
    const token = localStorage.getItem("access_token");
    const resp = await fetch("/api/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: token ? `Bearer ${token}` : "",
      },
      body: JSON.stringify({ conversation_id: currentId.value, question: q, stream: true }),
    });
    if (!resp.body) return;
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let eventName = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";
      for (const block of parts) {
        const lines = block.split("\n");
        for (const line of lines) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          if (line.startsWith("data:")) {
            try {
              const payload = JSON.parse(line.slice(5).trim());
              if (eventName === "delta") {
                assistant.content += payload.text || "";
                scrollToLatest();
              }
              if (eventName === "citation") {
                assistant.citations.push(payload);
                scrollToLatest();
              }
              if (eventName === "tool") {
                assistant.tools.push(payload);
                scrollToLatest();
              }
              if (eventName === "error") assistant.content += payload.message || "出错";
            } catch {
              continue;
            }
          }
        }
      }
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "发送失败");
    assistant.content = assistant.content || "发送失败";
  } finally {
    assistant.streaming = false;
    sending.value = false;
    await loadConvs();
  }
}

onMounted(async () => {
  await Promise.all([loadConvs(), loadKbs()]);
  if (currentId.value) {
    await loadMessages(currentId.value);
    if (!messages.value.length) await loadSuggestions(currentId.value);
    scrollToLatest();
  }
});

watch(currentId, async (id) => {
  suggestions.value = [];
  if (id) {
    await loadMessages(id);
    if (!messages.value.length) await loadSuggestions(id);
    scrollToLatest();
  } else {
    messages.value = [];
  }
});
</script>

<style scoped>
.chat-wrap {
  height: calc(100vh - 120px);
}
.chat-right {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.chat-main {
  padding: 0 !important;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.msg-pane {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px;
}
.aside {
  border-right: 1px solid #ebeef5;
  overflow: auto;
}
.conv-list {
  padding: 0 8px 12px;
}
.conv-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 8px 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  color: #303133;
}
.conv-item:hover,
.conv-item.menu-open {
  background: #f2f3f5;
}
.conv-item.active {
  background: #ecf5ff;
  color: #409eff;
}
.conv-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.conv-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}
.pin-dot {
  flex-shrink: 0;
  font-size: 12px;
}
.more-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #606266;
  font-size: 16px;
  letter-spacing: 1px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
}
.conv-item:hover .more-btn,
.conv-item.menu-open .more-btn {
  opacity: 1;
}
.more-btn:hover {
  background: #e4e7ed;
}
.danger-item {
  color: #f56c6c;
}
.hint {
  color: #909399;
  margin: 0 0 12px;
}
.composer {
  display: flex;
  gap: 8px;
  align-items: center;
}
.guides {
  max-width: 640px;
  margin: 24px auto 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.guide-title {
  margin: 0 0 4px;
  color: #303133;
  font-size: 15px;
  font-weight: 600;
}
.guide-empty {
  margin: 0;
  color: #909399;
  font-size: 13px;
}
.guide-card {
  text-align: left;
  padding: 12px 14px;
  border: 1px solid #dcdfe6;
  border-radius: 10px;
  background: #fff;
  color: #303133;
  font-size: 14px;
  line-height: 1.5;
  cursor: pointer;
}
.guide-card:hover:not(:disabled) {
  border-color: #409eff;
  background: #ecf5ff;
  color: #1d4ed8;
}
.guide-card:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}
</style>
