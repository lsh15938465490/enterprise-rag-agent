<template>
  <!-- 把 Markdown 渲染成 HTML；html:false 避免执行用户内容里的脚本 -->
  <div class="md" v-html="html" />
</template>

<script setup lang="ts">
import { computed } from "vue";
import { renderMarkdown } from "../lib/markdown";

const props = defineProps<{ content: string }>();
const html = computed(() => renderMarkdown(props.content));
</script>

<style scoped>
.md :deep(p) {
  margin: 0.4em 0;
}
.md :deep(pre) {
  background: #f5f7fa;
  padding: 8px;
  overflow: auto;
}
.md :deep(code) {
  font-family: Consolas, monospace;
}
</style>
