<template>
  <!-- 来源卡片：点标题展开原文片段，让用户核对答案从哪来 -->
  <el-card shadow="never" class="source">
    <div class="title" @click="open = !open">
      {{ filename }}
      <span v-if="pageNumber != null"> · 第 {{ pageNumber }} 页</span>
      <span v-if="heading"> · {{ heading }}</span>
      <el-tag size="small" style="margin-left: 8px">{{ score.toFixed(3) }}</el-tag>
    </div>
    <p v-show="open" class="snippet">{{ snippet }}</p>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from "vue";

defineProps<{
  filename: string;
  snippet: string;
  pageNumber?: number | null;
  heading?: string | null;
  score: number;
}>();

const open = ref(false);
</script>

<style scoped>
.source {
  margin-top: 8px;
}
.title {
  cursor: pointer;
  font-size: 13px;
}
.snippet {
  color: #606266;
  white-space: pre-wrap;
}
</style>
