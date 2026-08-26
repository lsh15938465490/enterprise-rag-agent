<template>
  <!-- 一条聊天：用户纯文本，助手 Markdown + 工具条 + 来源卡片 -->
  <div class="msg" :class="role">
    <b>{{ label }}</b>
    <p v-if="thinking" class="think">think<span class="dots">...</span></p>
    <el-alert
      v-for="(t, i) in processLogs"
      :key="i"
      :title="`${t.name} · ${t.status}`"
      :description="t.content"
      type="info"
      show-icon
      :closable="false"
      class="tool"
    />
    <StreamMarkdown v-if="role === 'assistant'" :content="content" />
    <div v-else class="user-body">{{ displayText }}</div>
    <SourceCard
      v-for="c in citations"
      :key="c.chunk_id"
      :filename="c.filename"
      :snippet="c.snippet"
      :page-number="c.page_number"
      :heading="c.heading"
      :score="c.score"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import SourceCard from "./SourceCard.vue";
import StreamMarkdown from "./StreamMarkdown.vue";
import { displayQuestion } from "../utils/questionText";

export interface Citation {
  chunk_id: string;
  filename: string;
  page_number: number | null;
  heading: string | null;
  score: number;
  snippet: string;
}

export interface ToolEvt {
  name: string;
  status: string;
  content: string;
}

const props = defineProps<{
  role: string;
  content: string;
  citations?: Citation[];
  tools?: ToolEvt[];
  thinking?: boolean;
  streaming?: boolean;
}>();

const citations = computed(() => props.citations || []);
const tools = computed(() => props.tools || []);
const processLogs = computed(() => (props.streaming ? tools.value : []));
const displayText = computed(() =>
  props.role === "user" ? displayQuestion(props.content) : props.content,
);
const label = computed(() => {
  if (props.role === "user") return "我";
  if (props.role === "assistant") return "助手";
  return props.role;
});
</script>

<style scoped>
.msg {
  margin-bottom: 16px;
}
.user-body {
  background: #f2f6fc;
  padding: 8px;
  border-radius: 6px;
  white-space: pre-wrap;
}
.tool {
  margin: 8px 0;
}
.think {
  margin: 8px 0 0;
  color: #909399;
  font-size: 14px;
  font-style: italic;
}
.dots {
  display: inline-block;
  animation: think-blink 1.2s steps(4, end) infinite;
}
@keyframes think-blink {
  0% {
    opacity: 0.2;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.2;
  }
}
</style>
