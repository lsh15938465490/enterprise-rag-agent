<template>
  <!-- 一条聊天：用户纯文本，助手 Markdown + 工具条 + 来源卡片 -->
  <div class="msg" :class="role">
    <b>{{ label }}</b>
    <el-alert
      v-for="(t, i) in tools"
      :key="i"
      :title="`${t.name} · ${t.status}`"
      :description="t.content"
      type="info"
      show-icon
      :closable="false"
      class="tool"
    />
    <StreamMarkdown v-if="role === 'assistant'" :content="content" />
    <div v-else class="user-body">{{ content }}</div>
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
}>();

const citations = computed(() => props.citations || []);
const tools = computed(() => props.tools || []);
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
</style>
