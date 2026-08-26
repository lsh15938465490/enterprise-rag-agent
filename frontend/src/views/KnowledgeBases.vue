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
      <el-table-column v-if="auth.isSuperAdmin" label="租户" width="140">
        <template #default="{ row }">{{ cellText(row.tenant_name || row.tenant_slug) }}</template>
      </el-table-column>
      <el-table-column label="名称" min-width="140">
        <template #default="{ row }">{{ cellText(row.name) }}</template>
      </el-table-column>
      <el-table-column label="描述" min-width="200">
        <template #default="{ row }">
          <span :class="{ muted: cellText(row.description) === EMPTY_CELL }">{{ cellText(row.description) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="启用" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "是" : "否" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="router.push(`/kbs/${row.id}/docs`)">文档</el-button>
          <el-button v-if="auth.isAdmin" link type="primary" @click.stop="openEdit(row)">编辑</el-button>
          <el-button v-if="auth.isAdmin" link type="primary" @click.stop="openAcl(row)">ACL</el-button>
          <el-button v-if="auth.isAdmin" link @click.stop="toggleActive(row)">{{ row.is_active ? "停用" : "启用" }}</el-button>
          <el-button v-if="auth.isAdmin" link type="danger" @click.stop="removeKb(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="dialog" title="新建知识库">
      <el-form label-position="top">
        <el-form-item v-if="auth.isSuperAdmin" label="部门">
          <el-select v-model="form.tenant_id" placeholder="请选择部门" style="width: 100%">
            <el-option v-for="t in depts" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="选填，列表中会展示" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false" :disabled="creating">取消</el-button>
        <el-button type="primary" :loading="creating" @click="create">确定</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="editVisible" title="编辑知识库">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="editForm.name" /></el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" placeholder="选填，列表中会展示" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveEdit">确定</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="aclVisible" title="知识库授权" width="560px">
      <p class="acl-hint">{{ aclHint }}</p>
      <el-table v-if="aclRows.length" :data="aclRows">
        <el-table-column prop="username" label="用户" />
        <el-table-column v-if="auth.isSuperAdmin" label="角色" width="100">
          <template #default="{ row }">{{ row.role === "tenant_admin" ? "管理者" : "普通用户" }}</template>
        </el-table-column>
        <el-table-column label="可读" width="100">
          <template #default="{ row }"><el-switch v-model="row.can_read" /></template>
        </el-table-column>
      </el-table>
      <p v-else class="acl-empty">暂无下级可授权</p>
      <template #footer>
        <el-button @click="aclVisible = false">取消</el-button>
        <el-button type="primary" @click="saveAcl">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";
import { useAuthStore } from "../stores/auth";
import { notifyLimit } from "../utils/notifyLimit";
import { cellText, EMPTY_CELL } from "../utils/emptyCell";

interface KB {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  tenant_id?: string;
  tenant_slug?: string | null;
  tenant_name?: string | null;
}

interface UserRow {
  id: string;
  username: string;
  role: string;
}

interface AclRow {
  user_id: string;
  username: string;
  role: string;
  can_read: boolean;
}

const router = useRouter();
const auth = useAuthStore();
const list = ref<KB[]>([]);
const dialog = ref(false);
const creating = ref(false);
const editVisible = ref(false);
const editSaving = ref(false);
const editKbId = ref("");
const aclVisible = ref(false);
const aclKbId = ref("");
const aclRows = ref<AclRow[]>([]);
const form = reactive({ name: "", description: "", tenant_id: "" });
const editForm = reactive({ name: "", description: "" });
const depts = ref<{ id: string; slug: string; name: string }[]>([]);
const aclHint = computed(() =>
  auth.isSuperAdmin
    ? "可配置该部门所有管理者和普通用户是否可读。取消勾选并保存后，对方知识库列表中立即看不到该库。"
    : "只配置下级普通用户是否可读。勾选后对方在「知识库」和「智能问答」中可见；当前登录账号不展示。",
);

async function load() {
  // 拉取我能看到的知识库
  const { data } = await http.get("/knowledge-bases");
  list.value = data.data || [];
}

async function loadDepts() {
  const { data } = await http.get("/auth/workspace-tenants");
  depts.value = data.data || [];
  if (!form.tenant_id && depts.value[0]) form.tenant_id = depts.value[0].id;
}

async function onCreateClick() {
  if (list.value.filter((k) => k.is_active && (!auth.isSuperAdmin || k.tenant_id === auth.user?.tenant_id)).length >= 10) {
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
  if (auth.isSuperAdmin && !form.tenant_id) {
    ElMessage.warning("请选择部门");
    return;
  }
  creating.value = true;
  try {
    const { data } = await http.post("/knowledge-bases", {
      name: form.name,
      description: form.description.trim() || null,
      tenant_id: auth.isSuperAdmin ? form.tenant_id : undefined,
    });
    ElMessage.success("已创建");
    dialog.value = false;
    form.name = "";
    form.description = "";
    const id = data.data?.id;
    if (id) {
      router.push(`/kbs/${id}/docs`);
      return;
    }
    await load();
  } finally {
    creating.value = false;
  }
}

async function openEdit(row: KB) {
  editKbId.value = row.id;
  editForm.name = row.name;
  editForm.description = row.description || "";
  editVisible.value = true;
}

async function saveEdit() {
  if (!editForm.name.trim()) {
    ElMessage.warning("请填写名称");
    return;
  }
  editSaving.value = true;
  try {
    await http.patch(`/knowledge-bases/${editKbId.value}`, {
      name: editForm.name.trim(),
      description: editForm.description.trim() || null,
    });
    ElMessage.success("已保存");
    editVisible.value = false;
    await load();
  } finally {
    editSaving.value = false;
  }
}

async function toggleActive(row: KB) {
  await http.patch(`/knowledge-bases/${row.id}`, { is_active: !row.is_active });
  ElMessage.success(row.is_active ? "已停用" : "已启用");
  await load();
}

async function removeKb(row: KB) {
  try {
    await ElMessageBox.confirm(`确认删除知识库「${row.name}」？删除后文档和向量不可恢复。`, "删除知识库", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      confirmButtonClass: "el-button--danger",
    });
  } catch {
    return;
  }
  await http.delete(`/knowledge-bases/${row.id}`);
  ElMessage.success("已删除");
  await load();
}

function isAclTarget(u: UserRow) {
  if (u.id === auth.user?.id || u.username === auth.user?.username) return false;
  if (u.role === "super_admin") return false;
  if (auth.isSuperAdmin) return true;
  return u.role !== "tenant_admin";
}

async function openAcl(row: KB) {
  aclKbId.value = row.id;
  let users: UserRow[] = [];
  try {
    const u = await http.get("/users", { params: { page_size: 100, tenant_id: row.tenant_id } });
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
  aclRows.value = users.filter(isAclTarget).map((u) => ({
    user_id: u.id,
    username: u.username,
    role: u.role,
    can_read: map.get(u.id)?.can_read || false,
  }));
  aclVisible.value = true;
}

async function saveAcl() {
  const items = aclRows.value
    .filter((r) => r.can_read)
    .map((r) => ({ user_id: r.user_id, can_read: true, can_write: false }));
  await http.put(`/knowledge-bases/${aclKbId.value}/acl`, { items });
  ElMessage.success("ACL 已保存");
  aclVisible.value = false;
}

onMounted(() => {
  load();
  if (auth.isSuperAdmin) loadDepts();
});
</script>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.muted {
  color: #c0c4cc;
}
.acl-hint {
  margin: 0 0 12px;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}
.acl-empty {
  margin: 0;
  color: #c0c4cc;
  font-size: 13px;
}
</style>
