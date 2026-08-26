<template>
  <!-- 历史会话列表：打开继续聊，删除需二次确认 -->
  <el-card header="历史会话">
    <el-table :data="items" @row-click="(row: Conv) => router.push(`/chat/${row.id}`)">
      <el-table-column label="标题" min-width="200">
        <template #default="{ row }">{{ cellText(row.title) }}</template>
      </el-table-column>
      <el-table-column v-if="auth.isSuperAdmin" label="租户" width="140">
        <template #default="{ row }">
          <el-tag v-if="row.tenant_name || row.tenant_slug" size="small" type="info">
            {{ row.tenant_name || row.tenant_slug }}
          </el-tag>
          <span v-else class="muted">{{ EMPTY_CELL }}</span>
        </template>
      </el-table-column>
      <el-table-column label="创建人" width="140">
        <template #default="{ row }">{{ cellText(row.owner_username) }}</template>
      </el-table-column>
      <el-table-column label="权限等级" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="roleType(row.owner_kind)">{{ cellText(row.owner_kind) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="模式" width="100">
        <template #default="{ row }">
          <el-tag size="small">{{ cellText(row.mode) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="180">
        <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="router.push(`/chat/${row.id}`)">打开</el-button>
          <el-button link type="danger" @click.stop="removeConv(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";
import { useAuthStore } from "../stores/auth";
import { EMPTY_CELL, cellText } from "../utils/emptyCell";

interface Conv {
  id: string;
  title: string;
  mode: string;
  updated_at: string;
  owner_kind?: string;
  owner_username?: string;
  tenant_slug?: string | null;
  tenant_name?: string | null;
}

const router = useRouter();
const auth = useAuthStore();
const items = ref<Conv[]>([]);

function roleType(kind?: string) {
  if (kind === "超级管理员") return "warning";
  if (kind === "管理者") return "warning";
  return "info";
}

function formatTime(iso: string) {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return EMPTY_CELL;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

async function load() {
  const pageSize = 100;
  const all: Conv[] = [];
  let page = 1;
  let total = Infinity;
  while (all.length < total) {
    const { data } = await http.get("/conversations", { params: { page, page_size: pageSize } });
    const chunk: Conv[] = data.data.items || [];
    total = data.data.total ?? chunk.length;
    all.push(...chunk);
    if (!chunk.length || chunk.length < pageSize) break;
    page += 1;
  }
  items.value = all;
}

async function removeConv(row: Conv) {
  try {
    await ElMessageBox.confirm(`确认删除对话「${row.title}」？删除后不可恢复。`, "是否删除对话？", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      confirmButtonClass: "el-button--danger",
    });
  } catch {
    return;
  }
  await http.delete(`/conversations/${row.id}`);
  ElMessage.success("已删除");
  await load();
}

onMounted(load);
</script>

<style scoped>
.muted {
  color: #c0c4cc;
}
</style>
