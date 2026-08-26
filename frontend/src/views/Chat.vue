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
            <el-option
              v-for="k in kbs"
              :key="k.id"
              :label="auth.isSuperAdmin && (k.tenant_name || k.tenant_slug) ? `${k.name}（${k.tenant_name || k.tenant_slug}）` : k.name"
              :value="k.id"
            />
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
            <span v-if="auth.isAdmin" class="conv-owner">
              <el-tag size="small" :type="c.owner_kind === '普通用户' ? 'info' : 'warning'">
                {{ c.owner_kind }}
              </el-tag>
            </span>
            <span class="conv-mode">
              <el-tag size="small" type="info">{{ c.mode }}</el-tag>
            </span>
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
                <el-dropdown-item command="edit">编辑</el-dropdown-item>
                <el-dropdown-item command="delete" divided>
                  <span class="danger-item">删除</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <p v-if="listTotal > convs.length" class="conv-more">仅显示近 7 天内最近 {{ convs.length }} 个，更早的请到「历史会话」</p>
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
              {{ displayQuestion(q) }}
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
            :thinking="m.role === 'assistant' && Boolean(m.streaming) && !m.content"
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
  <el-dialog v-model="editVisible" title="编辑会话" width="480px" append-to-body @closed="editConvId = ''">
    <el-form label-position="top">
      <el-form-item label="对话名称">
        <el-input v-model="editForm.title" maxlength="256" show-word-limit placeholder="请输入会话名称" />
      </el-form-item>
      <el-form-item label="知识库">
        <el-select v-model="editForm.knowledge_base_ids" multiple placeholder="选择知识库" style="width: 100%">
          <el-option
            v-for="k in kbs"
            :key="k.id"
            :label="auth.isSuperAdmin && (k.tenant_name || k.tenant_slug) ? `${k.name}（${k.tenant_name || k.tenant_slug}）` : k.name"
            :value="k.id"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="editVisible = false">取消</el-button>
      <el-button type="primary" :loading="editSaving" @click="saveEdit">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// Chat.vue：loadKbs/loadConvs 拉列表；createConv 必须先选知识库；send 用 fetch 读 SSE。
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";
import { getAccessToken } from "../api/session";
import ChatMessage from "../components/ChatMessage.vue";
import { notifyLimit } from "../utils/notifyLimit";
import { displayQuestion } from "../utils/questionText";
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
  knowledge_base_ids?: string[];
}
interface KB {
  id: string;
  name: string;
  is_active?: boolean;
  tenant_slug?: string | null;
  tenant_name?: string | null;
}

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const convs = ref<Conv[]>([]);
const ownTotal = ref(0);
const listTotal = ref(0);
const maxConvs = ref(20);
const kbs = ref<KB[]>([]);
const messages = ref<Msg[]>([]);
const question = ref("");
const sending = ref(false);
const openMenuId = ref("");
const suggestions = ref<string[]>([]);
const guideLoading = ref(false);
const createForm = reactive({ knowledge_base_ids: [] as string[], mode: "rag", title: "新对话" });
const kbSelectRef = ref<{ blur: () => void } | null>(null);
const editVisible = ref(false);
const editSaving = ref(false);
const editConvId = ref("");
const editForm = reactive({ title: "", knowledge_base_ids: [] as string[] });

function closeKbDropdown() {
  // 选中一项后收起下拉，避免挡着新建会话按钮
  nextTick(() => kbSelectRef.value?.blur());
}

const currentId = computed(() => (route.params.conversationId as string) || "");
const currentConv = computed(() => convs.value.find((c) => c.id === currentId.value));
const msgPane = ref<HTMLElement | null>(null);

function ownConvCount() {
  return ownTotal.value;
}

function scrollToLatest() {
  // 把右侧对话滚到最底部，看到最新一条
  nextTick(() => {
    const el = msgPane.value;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  });
}

async function loadConvs() {
  const { data } = await http.get("/conversations", { params: { page_size: 10, recent: true } });
  convs.value = data.data.items || [];
  ownTotal.value = data.data.own_total ?? convs.value.length;
  listTotal.value = data.data.total ?? convs.value.length;
  if (data.data.max_conversations) maxConvs.value = data.data.max_conversations;
}
async function loadKbs() {
  // 新建/编辑会话只列出启用中的知识库，停用库仅出现在知识库管理页
  const { data } = await http.get("/knowledge-bases", { params: { for_qa: true } });
  kbs.value = (data.data || []).filter((k: KB) => k.is_active !== false);
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
    suggestions.value = (data.data.questions || []).map((q: string) => displayQuestion(q));
  } catch {
    suggestions.value = [];
  } finally {
    guideLoading.value = false;
  }
}

async function createConv() {
  // 必须先勾选知识库，否则检索没有范围
  if (ownConvCount() >= maxConvs.value) {
    notifyLimit(`新对话最多 ${maxConvs.value} 个，请先删除后再创建`);
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
  // 三点菜单：置顶 / 编辑 / 删除。点取消会抛异常，这里吞掉。
  try {
    if (cmd === "pin" || cmd === "unpin") {
      await http.patch(`/conversations/${conv.id}`, { is_pinned: cmd === "pin" });
      ElMessage.success(cmd === "pin" ? "已置顶" : "已取消置顶");
      await loadConvs();
      return;
    }
    if (cmd === "edit") {
      const { data } = await http.get(`/conversations/${conv.id}`);
      editConvId.value = conv.id;
      editForm.title = data.data.title || conv.title;
      const allowed = new Set(kbs.value.map((k) => k.id));
      editForm.knowledge_base_ids = (data.data.knowledge_base_ids || [])
        .map(String)
        .filter((id: string) => allowed.has(id));
      editVisible.value = true;
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

async function saveEdit() {
  const title = editForm.title.trim();
  if (!title) {
    ElMessage.warning("请填写对话名称");
    return;
  }
  if (!editForm.knowledge_base_ids.length) {
    ElMessage.warning("请至少选择一个知识库");
    return;
  }
  editSaving.value = true;
  try {
    await http.patch(`/conversations/${editConvId.value}`, {
      title,
      knowledge_base_ids: editForm.knowledge_base_ids,
    });
    ElMessage.success("已保存");
    editVisible.value = false;
    await loadConvs();
    if (currentId.value === editConvId.value && !messages.value.length) {
      await loadSuggestions(editConvId.value);
    }
  } finally {
    editSaving.value = false;
  }
}

async function sendGuide(q: string) {
  // 点引导问题：填入输入框并直接发送
  question.value = displayQuestion(q);
  suggestions.value = [];
  await send();
}

function bumpCurrentConv() {
  const id = currentId.value;
  if (!id) return;
  const idx = convs.value.findIndex((c) => c.id === id);
  if (idx === 0) return;
  if (idx > 0) {
    const [item] = convs.value.splice(idx, 1);
    convs.value.unshift(item);
  }
}

async function send() {
  // 用 fetch 读 SSE：axios 不好处理逐字流
  if (!currentId.value || !question.value.trim()) return;
  sending.value = true;
  const q = displayQuestion(question.value.trim());
  const convId = currentId.value;
  question.value = "";
  messages.value.push({ id: "tmp-user", role: "user", content: q, citations: [], tools: [] });
  const assistant: Msg = { id: "stream", role: "assistant", content: "", citations: [], tools: [], streaming: true };
  messages.value.push(assistant);
  bumpCurrentConv();
  scrollToLatest();
  try {
    const token = getAccessToken();
    const resp = await fetch("/api/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        Authorization: token ? `Bearer ${token}` : "",
      },
      body: JSON.stringify({ conversation_id: convId, question: q, stream: true }),
    });
    if (!resp.ok) {
      const raw = await resp.text();
      let msg = "发送失败";
      try {
        const parsed = JSON.parse(raw);
        msg = parsed.message || parsed.detail || msg;
      } catch {
        if (raw) msg = raw.slice(0, 200);
      }
      assistant.content = msg;
      return;
    }
    if (!resp.body) {
      assistant.content = "未收到模型回复";
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let eventName = "message";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      buf = buf.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";
      for (const block of parts) {
        if (!block.trim()) continue;
        eventName = "message";
        const dataLines: string[] = [];
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (!dataLines.length) continue;
        try {
          const payload = JSON.parse(dataLines.join("\n"));
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
    if (!assistant.content.trim()) {
      assistant.content = "未收到模型回复，请再试一次。";
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

const autoAskLock = ref(false);
const queuedAsk = ref("");

function pendingAsk(): string {
  const raw = route.query.q;
  return typeof raw === "string" ? displayQuestion(raw.trim()) : "";
}

async function consumeAutoAsk(id: string) {
  const q = queuedAsk.value || pendingAsk();
  if (!q || !id) return;
  if (autoAskLock.value || sending.value) return;
  autoAskLock.value = true;
  queuedAsk.value = q;
  suggestions.value = [];
  try {
    question.value = q;
    await send();
    if (route.query.q || route.query.kb) {
      await router.replace({ path: `/chat/${id}` });
    }
  } finally {
    queuedAsk.value = "";
    autoAskLock.value = false;
  }
}

async function launchFromQuery() {
  const kb = route.query.kb;
  const qraw = pendingAsk();
  if (typeof kb !== "string" || !qraw) return;
  if (ownConvCount() >= maxConvs.value) {
    notifyLimit(`新对话最多 ${maxConvs.value} 个，请先删除后再创建`);
    return;
  }
  createForm.knowledge_base_ids = [];
  queuedAsk.value = qraw;
  const { data } = await http.post("/conversations", {
    knowledge_base_ids: [kb],
    mode: createForm.mode || "rag",
    title: qraw.slice(0, 24),
  });
  await loadConvs();
  await router.replace({ path: `/chat/${data.data.id}`, query: { q: qraw } });
}

async function openConversation(id: string) {
  const ask = queuedAsk.value || pendingAsk();
  if (ask) {
    await consumeAutoAsk(id);
    return;
  }
  if (autoAskLock.value || sending.value) return;
  await loadMessages(id);
  if (autoAskLock.value || sending.value) return;
  if (!messages.value.length) await loadSuggestions(id);
  scrollToLatest();
}

onMounted(async () => {
  await Promise.all([loadConvs(), loadKbs()]);
  if (!currentId.value && route.query.kb && pendingAsk()) {
    await launchFromQuery();
  }
  if (currentId.value) await openConversation(currentId.value);
});

watch(currentId, async (id) => {
  suggestions.value = [];
  if (!id) {
    messages.value = [];
    return;
  }
  await openConversation(id);
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
.conv-more {
  margin: 8px 8px 0;
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
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
.conv-owner {
  flex: 0 0 5.6em;
  display: flex;
  justify-content: flex-start;
}
.conv-mode {
  flex: 0 0 3.4em;
  display: flex;
  justify-content: flex-start;
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
