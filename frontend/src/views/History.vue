<template>
  <!-- 历史会话列表，点进去继续聊 -->
  <el-card header="历史会话">
    <el-table :data="items" @row-click="(row: Conv) => router.push(`/chat/${row.id}`)">
      <el-table-column prop="title" label="标题" />
      <el-table-column label="模式" width="120">
        <template #default="{ row }">
          <el-tag size="small">{{ row.mode }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" />
      <el-table-column label="" width="100">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="router.push(`/chat/${row.id}`)">打开</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import http from "../api/http";

interface Conv {
  id: string;
  title: string;
  mode: string;
  updated_at: string;
}

const router = useRouter();
const items = ref<Conv[]>([]);

onMounted(async () => {
  const { data } = await http.get("/conversations", { params: { page_size: 50 } });
  items.value = data.data.items || [];
});
</script>
