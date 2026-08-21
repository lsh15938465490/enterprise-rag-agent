<template>
  <!-- 左侧：选知识库并新建会话；右侧：消息列表和输入框。发送走 SSE 流式接口。 -->
  <el-container class="chat-wrap">
    <el-aside width="280px" class="aside">
      <el-form label-position="top" style="padding: 0 8px 12px">
        <el-form-item label="知识库">
          <el-select v-model="createForm.knowledge_base_ids" multiple placeholder="选择知识库" style="width: 100%">
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
      <el-menu :default-active="currentId">
        <el-menu-item v-for="c in convs" :key="c.id" :index="c.id" @click="router.push(`/chat/${c.id}`)">
          <span>{{ c.title }}</span>
          <el-tag size="small" style="margin-left: 6px">{{ c.mode }}</el-tag>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-main>
        <el-empty v-if="!currentId" description="请选择或新建会话" />
        <template v-else>
          <p class="hint">当前模式：{{ currentConv?.mode || "-" }}</p>
          <ChatMessage
            v-for="m in messages"
            :key="m.id"
            :role="m.role"
            :content="m.content"
            :citations="m.citations"
            :tools="m.tools"
          />
        </template>
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
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import http from "../api/http";
import ChatMessage from "../components/ChatMessage.vue";

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
}
interface Conv {
  id: string;
  title: string;
  mode: string;
}
interface KB {
  id: string;
  name: string;
}

const route = useRoute();
const router = useRouter();
const convs = ref<Conv[]>([]);
const kbs = ref<KB[]>([]);
const messages = ref<Msg[]>([]);
const question = ref("");
const sending = ref(false);
const createForm = reactive({ knowledge_base_ids: [] as string[], mode: "rag", title: "新对话" });

const currentId = computed(() => (route.params.conversationId as string) || "");
const currentConv = computed(() => convs.value.find((c) => c.id === currentId.value));

async function loadConvs() {
  const { data } = await http.get("/conversations");
  convs.value = data.data.items || [];
}
async function loadKbs() {
  const { data } = await http.get("/knowledge-bases");
  kbs.value = data.data || [];
}
async function loadMessages(id: string) {
  const { data } = await http.get(`/conversations/${id}`);
  messages.value = (data.data.messages || []).map((m: Msg) => ({
    ...m,
    tools: m.tools || [],
    citations: m.citations || [],
  }));
}

async function createConv() {
  if (!createForm.knowledge_base_ids.length) {
    ElMessage.warning("请至少选择一个知识库");
    return;
  }
  const { data } = await http.post("/conversations", createForm);
  await loadConvs();
  router.push(`/chat/${data.data.id}`);
}

async function send() {
  if (!currentId.value || !question.value.trim()) return;
  sending.value = true;
  const q = question.value.trim();
  question.value = "";
  messages.value.push({ id: "tmp-user", role: "user", content: q, citations: [], tools: [] });
  const assistant: Msg = { id: "stream", role: "assistant", content: "", citations: [], tools: [] };
  messages.value.push(assistant);
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
              if (eventName === "delta") assistant.content += payload.text || "";
              if (eventName === "citation") assistant.citations.push(payload);
              if (eventName === "tool") assistant.tools.push(payload);
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
    sending.value = false;
    await loadConvs();
  }
}

onMounted(async () => {
  await Promise.all([loadConvs(), loadKbs()]);
  if (currentId.value) await loadMessages(currentId.value);
});

watch(currentId, (id) => {
  if (id) loadMessages(id);
  else messages.value = [];
});
</script>

<style scoped>
.chat-wrap {
  height: calc(100vh - 120px);
}
.aside {
  border-right: 1px solid #ebeef5;
  overflow: auto;
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
</style>
