<template>
  <!-- 知识库列表：点一行进文档页；管理员可配 ACL -->
  <el-card>
    <template #header>
      <div class="row">
        <span>知识库</span>
        <el-button v-if="auth.isAdmin" type="primary" @click="onCreateClick">新建</el-button>
      </div>
    </template>
    <el-table :data="list" @row-click="(row: KB) => router.push(`/kbs/${row.id}/docs`)">
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="description" label="描述" />
      <el-table-column label="启用" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "是" : "否" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="router.push(`/kbs/${row.id}/docs`)">文档</el-button>
          <el-button v-if="auth.isAdmin" link type="primary" @click.stop="openAcl(row)">ACL</el-button>
          <el-button v-if="auth.isAdmin" link @click.stop="toggleActive(row)">{{ row.is_active ? "停用" : "启用" }}</el-button>
          <el-button v-if="auth.isAdmin" link type="danger" @click.stop="removeKb(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="dialog" title="新建知识库">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="create">确定</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="aclVisible" title="知识库授权" width="640px">
      <el-table :data="aclRows">
        <el-table-column prop="username" label="用户" />
        <el-table-column label="可读" width="100">
          <template #default="{ row }"><el-switch v-model="row.can_read" /></template>
        </el-table-column>
        <el-table-column label="可写" width="100">
          <template #default="{ row }"><el-switch v-model="row.can_write" /></template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="aclVisible = false">取消</el-button>
        <el-button type="primary" @click="saveAcl">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";
import { useAuthStore } from "../stores/auth";
import { notifyLimit } from "../utils/notifyLimit";

interface KB {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
}

interface UserRow {
  id: string;
  username: string;
  role: string;
}

interface AclRow {
  user_id: string;
  username: string;
  can_read: boolean;
  can_write: boolean;
}

const router = useRouter();
const auth = useAuthStore();
const list = ref<KB[]>([]);
const dialog = ref(false);
const aclVisible = ref(false);
const aclKbId = ref("");
const aclRows = ref<AclRow[]>([]);
const form = reactive({ name: "", description: "" });

async function load() {
  // 拉取我能看到的知识库
  const { data } = await http.get("/knowledge-bases");
  list.value = data.data || [];
}

async function onCreateClick() {
  if (list.value.filter((k) => k.is_active).length >= 10) {
    notifyLimit("知识库最多 10 个，请先删除后再创建");
    return;
  }
  dialog.value = true;
}

async function create() {
  if (!form.name.trim()) {
    ElMessage.warning("请填写名称");
    return;
  }
  await http.post("/knowledge-bases", { name: form.name, description: form.description || null });
  ElMessage.success("已创建");
  dialog.value = false;
  form.name = "";
  form.description = "";
  await load();
}

async function toggleActive(row: KB) {
  await http.patch(`/knowledge-bases/${row.id}`, { is_active: !row.is_active });
  ElMessage.success(row.is_active ? "已停用" : "已启用");
  await load();
}

async function removeKb(row: KB) {
  await ElMessageBox.confirm(`停用知识库「${row.name}」？`, "确认", { type: "warning" });
  await http.delete(`/knowledge-bases/${row.id}`);
  ElMessage.success("已软删除");
  await load();
}

async function openAcl(row: KB) {
  aclKbId.value = row.id;
  let users: UserRow[] = [];
  try {
    const u = await http.get("/users", { params: { page_size: 100 } });
    users = u.data.data.items || [];
  } catch {
    ElMessage.warning("无权拉取用户列表，仅管理员可配置 ACL");
    return;
  }
  let saved: { user_id: string; can_read: boolean; can_write: boolean }[] = [];
  try {
    const a = await http.get(`/knowledge-bases/${row.id}/acl`);
    saved = a.data.data || [];
  } catch {
    saved = [];
  }
  const map = new Map(saved.map((x) => [x.user_id, x]));
  aclRows.value = users.map((u) => ({
    user_id: u.id,
    username: u.username,
    can_read: map.get(u.id)?.can_read || false,
    can_write: map.get(u.id)?.can_write || false,
  }));
  aclVisible.value = true;
}

async function saveAcl() {
  const items = aclRows.value
    .filter((r) => r.can_read || r.can_write)
    .map((r) => ({ user_id: r.user_id, can_read: r.can_read || r.can_write, can_write: r.can_write }));
  await http.put(`/knowledge-bases/${aclKbId.value}/acl`, { items });
  ElMessage.success("ACL 已保存");
  aclVisible.value = false;
}

onMounted(load);
</script>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
