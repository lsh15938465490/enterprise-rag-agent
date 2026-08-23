<template>
  <!-- 某个知识库下的文档：上传后轮询状态，ready 后才能被问答检索到 -->
  <el-card>
    <template #header>
      <div class="row">
        <span>
          <el-button link type="primary" @click="router.push('/kbs')">返回知识库</el-button>
          文档
        </span>
        <el-upload v-if="auth.isAdmin" :show-file-list="false" accept=".pdf,.docx,.txt,.md" :http-request="handleUpload" :before-upload="beforeUpload">
          <el-button type="primary" :loading="uploading">上传 PDF/DOCX/TXT/MD</el-button>
        </el-upload>
      </div>
    </template>
    <el-table :data="items">
      <el-table-column prop="filename" label="文件名" />
      <el-table-column label="状态" width="140">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="error_message" label="失败原因" />
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button link type="primary" @click="download(row)">下载</el-button>
          <el-button
            v-if="auth.isAdmin"
            link
            type="primary"
            :disabled="row.status === 'parsing'"
            @click="reprocess(row.id)"
          >
            重新解析
          </el-button>
          <el-button v-if="auth.isAdmin" link type="danger" @click="removeDoc(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <p v-if="pending" class="hint">解析进行中，列表每 3 秒自动刷新…</p>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";
import { notifyLimit } from "../utils/notifyLimit";
import { useAuthStore } from "../stores/auth";

interface Doc {
  id: string;
  filename: string;
  status: string;
  error_message: string | null;
  file_size: number;
  created_at: string;
}

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const kbId = computed(() => route.params.id as string);
const items = ref<Doc[]>([]);
const uploading = ref(false);
let timer: number | undefined;

const pending = computed(() =>
  items.value.some((d) => ["uploaded", "parsing", "parsed", "embedding"].includes(d.status)),
);

function statusType(s: string) {
  // 表格里不同状态用不同颜色的标签
  if (s === "ready") return "success";
  if (s === "failed") return "danger";
  return "warning";
}

async function load() {
  // 拉取当前知识库的文档列表
  const { data } = await http.get(`/knowledge-bases/${kbId.value}/documents`);
  items.value = data.data.items || [];
}

function startPoll() {
  stopPoll();
  timer = window.setInterval(() => {
    if (pending.value) load();
  }, 3000);
}

function stopPoll() {
  if (timer) {
    window.clearInterval(timer);
    timer = undefined;
  }
}

function beforeUpload(file: File) {
  // 超限或同名时拦截上传，并弹出 3 秒提示
  if (items.value.length >= 5) {
    notifyLimit("每个知识库最多上传 5 份文档，请先删除后再上传", "无法上传");
    return false;
  }
  if (items.value.some((d) => d.filename === file.name)) {
    notifyLimit("已经有相同名字的文档，请修改名字后重新上传", "无法上传");
    return false;
  }
  return true;
}

async function onFile(file: File) {
  uploading.value = true;
  try {
    const form = new FormData();
    form.append("file", file);
    await http.post(`/knowledge-bases/${kbId.value}/documents`, form);
    ElMessage.success("已上传，正在解析");
    await load();
  } finally {
    uploading.value = false;
  }
}

async function reprocess(id: string) {
  await http.post(`/documents/${id}/reprocess`);
  ElMessage.success("已重新解析");
  await load();
}

async function download(row: Doc) {
  const token = localStorage.getItem("access_token");
  const resp = await fetch(`/api/v1/documents/${row.id}/file`, {
    headers: { Authorization: token ? `Bearer ${token}` : "" },
  });
  if (!resp.ok) {
    ElMessage.error("下载失败");
    return;
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = row.filename;
  a.click();
  URL.revokeObjectURL(url);
}

async function removeDoc(row: Doc) {
  await ElMessageBox.confirm(`删除「${row.filename}」？`, "确认", { type: "warning" });
  await http.delete(`/documents/${row.id}`);
  ElMessage.success("已删除");
  await load();
}

async function handleUpload(opt: { file: File; onSuccess?: (r: unknown) => void; onError?: (e: Error) => void }) {
  try {
    await onFile(opt.file);
    opt.onSuccess?.({});
  } catch (e) {
    opt.onError?.(e as Error);
  }
}

onMounted(async () => {
  await load();
  startPoll();
});
onUnmounted(stopPoll);
</script>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.hint {
  color: #909399;
  margin-top: 12px;
}
</style>
