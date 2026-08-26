<template>
  <!-- 某个知识库下的文档：上传后轮询；解析完成在右侧展示切块数和示例问题 -->
  <div class="docs-page">
    <el-card class="docs-main">
      <template #header>
        <div class="row">
          <span>
            <el-button link type="primary" @click="router.push('/kbs')">返回知识库</el-button>
            文档
          </span>
          <div class="header-actions">
            <span class="tenant-label">所属租户：</span>
            <el-select
              v-model="selectedTenantId"
              placeholder="请选择"
              style="width: 180px"
              :disabled="!auth.isSuperAdmin"
              @change="onTenantChange"
            >
              <el-option v-for="t in tenants" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
            <el-button
              v-if="auth.isAdmin"
              type="primary"
              :loading="uploading"
              :disabled="remainingSlots <= 0 && !uploading"
              @click="sourceDialog = true"
            >
              上传文件（剩余上传数量{{ remainingSlots }}）
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="items" highlight-current-row @row-click="onRowClick">
        <el-table-column prop="filename" label="文件名">
          <template #default="{ row }">{{ cellText(row.filename) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ cellText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="失败原因">
          <template #default="{ row }">
            <span :class="{ muted: !row.error_message }">{{ cellText(row.error_message) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="download(row)">下载</el-button>
            <el-button
              v-if="auth.isAdmin"
              link
              type="primary"
              :disabled="row.status === 'parsing'"
              @click.stop="reprocess(row.id)"
            >
              重新解析
            </el-button>
            <el-button v-if="auth.isAdmin" link type="danger" @click.stop="removeDoc(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p v-if="pending" class="hint">解析进行中，列表每 3 秒自动刷新…</p>
    </el-card>
    <el-card v-if="preview || previewLoading" class="docs-side">
      <template #header>解析结果</template>
      <p v-if="previewLoading" class="hint">正在生成切块统计和示例问题…</p>
      <template v-else-if="preview">
        <p class="chunk-line">
          该文档被切成了 <strong>{{ preview.chunk_count }}</strong> 个 chunk
        </p>
        <p class="sub">Agent 示例问题（点击可去问答页测试）</p>
        <button
          v-for="item in preview.questions"
          :key="item.question"
          type="button"
          class="q-card"
          @click="testQuestion(item.question)"
        >
          <span>{{ item.question }}</span>
          <span v-if="item.low_recall" class="warn" title="该问题召回率偏低">⚠</span>
        </button>
        <p v-if="!preview.questions.length" class="hint">暂未生成示例问题</p>
      </template>
    </el-card>
    <el-dialog v-model="sourceDialog" title="选择上传方式" width="420px" :close-on-click-modal="!uploading">
      <div class="source-actions">
        <el-upload
          ref="uploadRef"
          multiple
          :limit="uploadLimit"
          :show-file-list="false"
          accept=".pdf,.docx,.txt,.md"
          :disabled="uploading || remainingSlots <= 0"
          :http-request="handleUpload"
          :before-upload="beforeUpload"
          :on-exceed="onExceed"
        >
          <el-button type="primary" :loading="uploading" :disabled="remainingSlots <= 0">
            上传 PDF/DOCX/TXT/MD
          </el-button>
        </el-upload>
        <el-button :disabled="remainingSlots <= 0" @click="openAiCreate">AI 创作</el-button>
      </div>
    </el-dialog>
    <el-dialog
      v-model="aiDialog"
      title="AI 生成文档"
      width="720px"
      :close-on-click-modal="!aiGenerating && !aiSaving"
      @closed="onAiDialogClosed"
    >
      <el-form label-position="top">
        <el-form-item label="文档标题" required>
          <el-input v-model="aiTitle" maxlength="200" placeholder="例如：公司请假流程 SOP" :disabled="aiGenerating" />
        </el-form-item>
        <el-form-item label="内容要求 / 描述" required>
          <el-input
            v-model="aiRequirements"
            type="textarea"
            :rows="4"
            maxlength="8000"
            placeholder="例如：生成一份关于公司请假流程的 SOP 文档"
            :disabled="aiGenerating"
          />
        </el-form-item>
      </el-form>
      <div class="ai-toolbar">
        <el-button type="primary" :loading="aiGenerating" :disabled="!canGenerate" @click="generateAiDoc">
          开始生成
        </el-button>
        <span v-if="aiColdStart" class="hint">当前知识库暂无参考片段，将按冷启动规则生成初稿。</span>
      </div>
      <p v-if="aiCitations.length" class="sub">引用来源（与正文 [S1][S2] 对应）</p>
      <ul v-if="aiCitations.length" class="cite-list">
        <li v-for="(c, i) in aiCitations" :key="c.chunk_id || i">
          [S{{ i + 1 }}] {{ c.filename }} 页 {{ c.page_number || "-" }}
          <span v-if="c.heading"> · {{ c.heading }}</span>
        </li>
      </ul>
      <el-input
        v-model="aiContent"
        type="textarea"
        :rows="14"
        placeholder="生成结果将在此流式展示，可直接编辑后再保存入库"
      />
      <template #footer>
        <el-button @click="aiDialog = false" :disabled="aiGenerating">取消</el-button>
        <el-button type="primary" :loading="aiSaving" :disabled="aiGenerating || !aiContent.trim()" @click="saveAiDoc">
          保存入库
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";
import { getAccessToken } from "../api/session";
import { notifyLimit } from "../utils/notifyLimit";
import { cellText } from "../utils/emptyCell";
import { useAuthStore } from "../stores/auth";

interface Doc {
  id: string;
  filename: string;
  status: string;
  error_message: string | null;
  file_size: number;
  created_at: string;
}

interface SampleQ {
  question: string;
  score: number;
  low_recall: boolean;
}

interface Preview {
  document_id: string;
  filename: string;
  chunk_count: number;
  questions: SampleQ[];
}

interface TenantOpt {
  id: string;
  slug: string;
  name: string;
}

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const kbId = computed(() => route.params.id as string);
const items = ref<Doc[]>([]);
const uploading = ref(false);
const sourceDialog = ref(false);
const uploadRef = ref<{ clearFiles: () => void } | null>(null);
const maxDocs = ref(5);
const maxUploadMb = ref(50);
const remainingSlots = computed(() => Math.max(0, maxDocs.value - items.value.length));
const uploadLimit = computed(() => Math.max(1, remainingSlots.value));
const ALLOWED_EXT = [".pdf", ".docx", ".txt", ".md"];
const aiDialog = ref(false);
const aiTitle = ref("");
const aiRequirements = ref("");
const aiContent = ref("");
const aiGenerating = ref(false);
const aiSaving = ref(false);
const aiColdStart = ref(false);
const aiCitations = ref<
  { chunk_id?: string; filename: string; page_number?: number | null; heading?: string | null }[]
>([]);
let aiAbort: AbortController | null = null;
const canGenerate = computed(
  () => Boolean(aiTitle.value.trim() && aiRequirements.value.trim()) && remainingSlots.value > 0,
);

type UploadTask = {
  file: File;
  onSuccess?: (r: unknown) => void;
  onError?: (e: Error) => void;
};
const uploadQueue: UploadTask[] = [];
const stagingNames = ref<string[]>([]);
let flushTimer: number | undefined;
const tenants = ref<TenantOpt[]>([]);
const selectedTenantId = ref("");
const preview = ref<Preview | null>(null);
const previewLoading = ref(false);
const watchingId = ref("");
let loadedPreviewFor = "";
let timer: number | undefined;

const pending = computed(() =>
  items.value.some((d) => ["uploaded", "parsing", "parsed", "embedding"].includes(d.status)),
);

function statusType(s: string) {
  if (s === "ready") return "success";
  if (s === "failed") return "danger";
  return "warning";
}

async function loadKbTenant() {
  const { data } = await http.get(`/knowledge-bases/${kbId.value}`);
  selectedTenantId.value = data.data.tenant_id || "";
}

async function loadTenants() {
  const { data } = await http.get(auth.isSuperAdmin ? "/auth/workspace-tenants" : "/auth/tenants");
  tenants.value = data.data || [];
  if (!auth.isSuperAdmin && auth.user?.tenant_id) {
    selectedTenantId.value = auth.user.tenant_id;
  }
}

async function load() {
  const { data } = await http.get(`/knowledge-bases/${kbId.value}/documents`);
  items.value = data.data.items || [];
  const target = watchingId.value && items.value.find((d) => d.id === watchingId.value);
  if (target?.status === "ready" && loadedPreviewFor !== target.id) {
    await loadPreview(target.id);
  }
}

async function loadPreview(id: string) {
  previewLoading.value = true;
  try {
    const { data } = await http.get(`/documents/${id}/ingest-preview`, { timeout: 120000 });
    preview.value = data.data;
    loadedPreviewFor = id;
  } catch {
    preview.value = null;
  } finally {
    previewLoading.value = false;
  }
}

async function onRowClick(row: Doc) {
  if (row.status !== "ready") {
    watchingId.value = row.id;
    preview.value = null;
    return;
  }
  watchingId.value = row.id;
  await loadPreview(row.id);
}

async function onTenantChange(id: string) {
  const { data } = await http.get("/knowledge-bases");
  const kbs = (data.data || []).filter((k: { id: string; tenant_id?: string }) => k.tenant_id === id);
  if (!kbs.length) {
    ElMessage.warning("该租户下还没有知识库");
    await loadKbTenant();
    return;
  }
  if (kbs.some((k: { id: string }) => k.id === kbId.value)) return;
  router.push(`/kbs/${kbs[0].id}/docs`);
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

function fileSuffix(name: string) {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

async function matchesMagic(file: File): Promise<boolean> {
  const head = new Uint8Array(await file.slice(0, 8).arrayBuffer());
  const ext = fileSuffix(file.name);
  const pdf = head[0] === 0x25 && head[1] === 0x50 && head[2] === 0x44 && head[3] === 0x46;
  const zip = head[0] === 0x50 && head[1] === 0x4b;
  const exe = head[0] === 0x4d && head[1] === 0x5a;
  const ole = head[0] === 0xd0 && head[1] === 0xcf;
  if (ext === ".pdf") return pdf;
  if (ext === ".docx") return zip;
  if (ext === ".txt" || ext === ".md") return !pdf && !zip && !exe && !ole;
  return false;
}

async function beforeUpload(file: File) {
  if (!ALLOWED_EXT.includes(fileSuffix(file.name))) {
    notifyLimit("仅支持 PDF / DOCX / TXT / MD", "无法上传");
    return false;
  }
  if (file.size > maxUploadMb.value * 1024 * 1024) {
    notifyLimit(`单个文件不能超过 ${maxUploadMb.value}MB`, "无法上传");
    return false;
  }
  const taken = new Set([...items.value.map((d) => d.filename), ...stagingNames.value]);
  if (taken.has(file.name)) {
    notifyLimit("已经有相同名字的文档，请修改名字后重新上传", "无法上传");
    return false;
  }
  if (items.value.length + stagingNames.value.length >= maxDocs.value) {
    notifyLimit(`每个知识库最多上传 ${maxDocs.value} 份文档，请先删除后再上传`, "无法上传");
    return false;
  }
  if (!(await matchesMagic(file))) {
    notifyLimit("文件内容与后缀不一致", "无法上传");
    return false;
  }
  stagingNames.value.push(file.name);
  return true;
}

function onExceed() {
  notifyLimit(`每个知识库最多上传 ${maxDocs.value} 份文档，本次还可选 ${remainingSlots.value} 个`, "无法上传");
}

function openAiCreate() {
  if (remainingSlots.value <= 0) {
    notifyLimit(`每个知识库最多上传 ${maxDocs.value} 份文档，请先删除后再创作`, "无法创作");
    return;
  }
  sourceDialog.value = false;
  aiTitle.value = "";
  aiRequirements.value = "";
  aiContent.value = "";
  aiCitations.value = [];
  aiColdStart.value = false;
  aiDialog.value = true;
}

function onAiDialogClosed() {
  aiAbort?.abort();
  aiAbort = null;
  aiGenerating.value = false;
}

async function generateAiDoc() {
  if (!canGenerate.value) return;
  aiAbort?.abort();
  aiAbort = new AbortController();
  aiGenerating.value = true;
  aiContent.value = "";
  aiCitations.value = [];
  aiColdStart.value = false;
  try {
    const token = getAccessToken();
    const resp = await fetch("/api/v1/ai/generate-document", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        Authorization: token ? `Bearer ${token}` : "",
      },
      body: JSON.stringify({
        knowledge_base_id: kbId.value,
        title: aiTitle.value.trim(),
        requirements: aiRequirements.value.trim(),
        stream: true,
      }),
      signal: aiAbort.signal,
    });
    if (!resp.ok) {
      const raw = await resp.text();
      let msg = "生成失败";
      try {
        const parsed = JSON.parse(raw);
        msg = parsed.message || parsed.detail || msg;
      } catch {
        if (raw) msg = raw.slice(0, 200);
      }
      ElMessage.error(msg);
      return;
    }
    if (!resp.body) {
      ElMessage.error("未收到生成内容");
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      buf = buf.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";
      for (const block of parts) {
        if (!block.trim()) continue;
        let eventName = "message";
        const dataLines: string[] = [];
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (!dataLines.length) continue;
        const payload = JSON.parse(dataLines.join("\n"));
        if (eventName === "meta") aiColdStart.value = Boolean(payload.cold_start);
        if (eventName === "citation") aiCitations.value.push(payload);
        if (eventName === "delta") aiContent.value += payload.text || "";
        if (eventName === "error") {
          ElMessage.error(payload.message || "模型调用失败");
        }
      }
    }
    if (!aiContent.value.trim()) ElMessage.warning("未生成有效内容，请调整要求后重试");
  } catch (e) {
    if ((e as Error).name !== "AbortError") ElMessage.error("生成失败");
  } finally {
    aiGenerating.value = false;
  }
}

async function saveAiDoc() {
  if (!aiContent.value.trim() || !aiTitle.value.trim()) {
    ElMessage.warning("请填写标题并生成或编辑正文后再保存");
    return;
  }
  if (remainingSlots.value <= 0) {
    notifyLimit(`每个知识库最多上传 ${maxDocs.value} 份文档，请先删除后再保存`, "无法保存");
    return;
  }
  aiSaving.value = true;
  try {
    const { data } = await http.post("/ai/save-document", {
      knowledge_base_id: kbId.value,
      title: aiTitle.value.trim(),
      content: aiContent.value,
    });
    const doc = data.data;
    watchingId.value = doc?.id || "";
    loadedPreviewFor = "";
    preview.value = null;
    ElMessage.success("已保存，正在解析入库");
    aiDialog.value = false;
    await load();
  } finally {
    aiSaving.value = false;
  }
}

async function flushUploads() {
  const batch = uploadQueue.splice(0, uploadQueue.length);
  if (!batch.length) {
    stagingNames.value = [];
    return;
  }
  uploading.value = true;
  try {
    const form = new FormData();
    for (const task of batch) form.append("files", task.file);
    const { data } = await http.post(`/knowledge-bases/${kbId.value}/documents/batch`, form, { timeout: 180000 });
    const created = data.data || [];
    const last = created[created.length - 1];
    watchingId.value = last?.id || "";
    loadedPreviewFor = "";
    preview.value = null;
    ElMessage.success(batch.length > 1 ? `已上传 ${batch.length} 个文件，正在解析` : "已上传，正在解析");
    await load();
    sourceDialog.value = false;
    for (const task of batch) task.onSuccess?.({});
  } catch (e) {
    for (const task of batch) task.onError?.(e as Error);
  } finally {
    stagingNames.value = [];
    uploading.value = false;
    uploadRef.value?.clearFiles();
  }
}

function handleUpload(opt: UploadTask) {
  uploadQueue.push(opt);
  uploading.value = true;
  if (flushTimer) window.clearTimeout(flushTimer);
  flushTimer = window.setTimeout(flushUploads, 80);
}

async function reprocess(id: string) {
  await http.post(`/documents/${id}/reprocess`);
  watchingId.value = id;
  loadedPreviewFor = "";
  preview.value = null;
  ElMessage.success("已重新解析");
  await load();
}

async function download(row: Doc) {
  const token = getAccessToken();
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
  if (watchingId.value === row.id) {
    watchingId.value = "";
    preview.value = null;
    loadedPreviewFor = "";
  }
  ElMessage.success("已删除");
  await load();
}

function testQuestion(q: string) {
  router.push({ path: "/chat", query: { kb: kbId.value, q } });
}

watch(kbId, async () => {
  preview.value = null;
  watchingId.value = "";
  loadedPreviewFor = "";
  await loadKbTenant();
  await load();
});

onMounted(async () => {
  try {
    const { data } = await http.get("/system/limits");
    if (data.data?.max_documents_per_kb) maxDocs.value = data.data.max_documents_per_kb;
    if (data.data?.max_upload_mb) maxUploadMb.value = data.data.max_upload_mb;
  } catch {
    /* 使用默认上限 */
  }
  await Promise.all([loadTenants(), loadKbTenant(), load()]);
  startPoll();
});
onUnmounted(() => {
  if (flushTimer) window.clearTimeout(flushTimer);
  stopPoll();
  aiAbort?.abort();
});
</script>

<style scoped>
.docs-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 16px;
  align-items: start;
}
@media (max-width: 960px) {
  .docs-page {
    grid-template-columns: 1fr;
  }
}
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.source-actions {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
}
.source-actions :deep(.el-upload),
.source-actions :deep(.el-upload .el-button) {
  width: 100%;
}
.tenant-label {
  color: #606266;
  font-size: 14px;
  white-space: nowrap;
}
.hint {
  color: #909399;
  margin-top: 12px;
}
.chunk-line {
  margin: 0 0 12px;
}
.sub {
  color: #909399;
  font-size: 13px;
  margin: 0 0 8px;
}
.q-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  text-align: left;
  margin-bottom: 8px;
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  line-height: 1.5;
}
.q-card:hover {
  border-color: #409eff;
}
.warn {
  color: #e6a23c;
  font-size: 18px;
  line-height: 1;
  flex-shrink: 0;
}
.muted {
  color: #c0c4cc;
}
.ai-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 12px;
}
.cite-list {
  margin: 0 0 12px;
  padding-left: 18px;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}
</style>
