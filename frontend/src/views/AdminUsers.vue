<template>
  <!-- 管理员：搜索、新建用户、改角色、启用/禁用 -->
  <el-card>
    <template #header>
      <div class="row">
        <span>权限管理</span>
        <div class="actions">
          <el-input v-model="keyword" placeholder="搜索用户名/邮箱" clearable style="width: 220px" @keyup.enter="load" />
          <el-button @click="load">搜索</el-button>
          <el-button type="primary" @click="dialog = true">新建用户</el-button>
        </div>
      </div>
    </template>
    <el-table :data="items">
      <el-table-column v-if="auth.isSuperAdmin" label="部门" width="120">
        <template #default="{ row }">{{ cellText(row.tenant_name) }}</template>
      </el-table-column>
      <el-table-column label="用户名">
        <template #default="{ row }">{{ cellText(row.username) }}</template>
      </el-table-column>
      <el-table-column label="邮箱">
        <template #default="{ row }">{{ cellText(row.email) }}</template>
      </el-table-column>
      <el-table-column label="登录时间" width="200">
        <template #default="{ row }">
          <el-tooltip v-if="row.logins && row.logins.length" placement="top" :show-after="200">
            <template #content>
              <div class="login-tip">
                <div v-for="(item, idx) in row.logins" :key="idx">{{ cellText(item.logged_at) }}　{{ cellText(item.device_name) }}</div>
              </div>
            </template>
            <span class="login-cell">
              {{ cellText(row.last_login_at) }}<span v-if="row.login_count && row.login_count > 1">...</span>
            </span>
          </el-tooltip>
          <span v-else class="login-empty">{{ EMPTY_CELL }}</span>
        </template>
      </el-table-column>
      <el-table-column label="角色" width="180">
        <template #default="{ row }">
          <el-select
            :model-value="row.role"
            size="small"
            :disabled="!canChangeRole(row)"
            @change="(v: string) => changeRole(row, v)"
          >
            <el-option v-if="row.role === 'super_admin'" label="超级管理员" value="super_admin" />
            <el-option label="普通用户" value="member" />
            <el-option label="管理者" value="tenant_admin" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "启用" : "禁用" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <template v-if="!isProtected(row)">
            <el-button link type="primary" @click="toggleActive(row)">
              {{ row.is_active ? "禁用" : "启用" }}
            </el-button>
            <el-button link type="danger" @click="removeUser(row)">删除</el-button>
          </template>
          <span v-else class="locked">不可降级</span>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="dialog" title="新建用户">
      <el-form label-position="top">
        <el-form-item v-if="auth.isSuperAdmin" label="部门">
          <el-select v-model="form.tenant_id" placeholder="请选择部门" style="width: 100%">
            <el-option v-for="t in depts" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role">
            <el-option label="普通用户" value="member" />
            <el-option label="管理者" value="tenant_admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="create">确定</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";
import { useAuthStore } from "../stores/auth";
import { EMPTY_CELL, cellText } from "../utils/emptyCell";

interface LoginRecord {
  logged_at: string;
  device_name: string;
}

interface UserRow {
  id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  tenant_name?: string | null;
  last_login_at?: string | null;
  login_count?: number;
  logins?: LoginRecord[];
}

const items = ref<UserRow[]>([]);
const keyword = ref("");
const dialog = ref(false);
const auth = useAuthStore();
const depts = ref<{ id: string; slug: string; name: string }[]>([]);
const form = reactive({ username: "", email: "", password: "", role: "member", tenant_id: "" });

function isProtected(row: UserRow) {
  return row.username === "adminliu" || row.role === "super_admin";
}

function isSelf(row: UserRow) {
  return row.id === auth.user?.id || row.username === auth.user?.username;
}

function canChangeRole(row: UserRow) {
  if (isProtected(row)) return false;
  if (auth.isSuperAdmin) return true;
  return Boolean(auth.user) && !isSelf(row);
}

async function loadDepts() {
  const { data } = await http.get("/auth/tenants");
  depts.value = data.data || [];
  if (!form.tenant_id && depts.value[0]) form.tenant_id = depts.value[0].id;
}

async function load() {
  // 管理员用户列表，支持关键字
  const { data } = await http.get("/users", { params: { keyword: keyword.value || undefined, page_size: 50 } });
  items.value = data.data.items || [];
}

async function create() {
  if (auth.isSuperAdmin && !form.tenant_id) {
    ElMessage.warning("请选择部门");
    return;
  }
  if (!/^(?=.*[A-Za-z])(?=.*\d).{8,}$/.test(form.password)) {
    ElMessage.error("密码至少 8 位且包含字母和数字");
    return;
  }
  const payload: Record<string, string> = {
    username: form.username,
    email: form.email,
    password: form.password,
    role: form.role,
  };
  if (auth.isSuperAdmin) payload.tenant_id = form.tenant_id;
  await http.post("/users", payload);
  ElMessage.success("已创建");
  dialog.value = false;
  form.username = "";
  form.email = "";
  form.password = "";
  form.role = "member";
  await load();
}

async function changeRole(row: UserRow, role: string) {
  if (!canChangeRole(row)) {
    ElMessage.warning("不能修改自己的角色");
    return;
  }
  await http.patch(`/users/${row.id}`, { role });
  ElMessage.success("角色已更新");
  await load();
}

async function toggleActive(row: UserRow) {
  await http.patch(`/users/${row.id}`, { is_active: !row.is_active });
  ElMessage.success(row.is_active ? "已禁用" : "已启用");
  await load();
}

async function removeUser(row: UserRow) {
  try {
    await ElMessageBox.confirm(`确认删除用户「${row.username}」？删除后不可恢复。`, "删除用户", {
      type: "warning",
      confirmButtonText: "确认删除",
      cancelButtonText: "取消",
      confirmButtonClass: "el-button--danger",
    });
  } catch {
    return;
  }
  await http.delete(`/users/${row.id}`);
  ElMessage.success("已删除");
  await load();
}

onMounted(() => {
  load();
  loadDepts();
});
</script>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.locked {
  color: #909399;
  font-size: 12px;
}
.login-cell {
  cursor: default;
  white-space: nowrap;
}
.login-empty {
  color: #c0c4cc;
}
.login-tip {
  max-height: 280px;
  overflow: auto;
  line-height: 1.6;
  font-size: 12px;
}
</style>
