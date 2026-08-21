<template>
  <!-- 管理员：搜索、新建用户、改角色、启用/禁用 -->
  <el-card>
    <template #header>
      <div class="row">
        <span>用户管理</span>
        <div class="actions">
          <el-input v-model="keyword" placeholder="搜索用户名/邮箱" clearable style="width: 220px" @keyup.enter="load" />
          <el-button @click="load">搜索</el-button>
          <el-button type="primary" @click="dialog = true">新建用户</el-button>
        </div>
      </div>
    </template>
    <el-table :data="items">
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="email" label="邮箱" />
      <el-table-column label="角色" width="180">
        <template #default="{ row }">
          <el-select :model-value="row.role" size="small" @change="(v: string) => changeRole(row, v)">
            <el-option label="member" value="member" />
            <el-option label="kb_editor" value="kb_editor" />
            <el-option label="tenant_admin" value="tenant_admin" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "启用" : "禁用" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button link type="primary" @click="toggleActive(row)">
            {{ row.is_active ? "禁用" : "启用" }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="dialog" title="新建用户">
      <el-form label-position="top">
        <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role">
            <el-option label="member" value="member" />
            <el-option label="kb_editor" value="kb_editor" />
            <el-option label="tenant_admin" value="tenant_admin" />
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
import { ElMessage } from "element-plus";
import http from "../api/http";

interface UserRow {
  id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
}

const items = ref<UserRow[]>([]);
const keyword = ref("");
const dialog = ref(false);
const form = reactive({ username: "", email: "", password: "", role: "member" });

async function load() {
  const { data } = await http.get("/users", { params: { keyword: keyword.value || undefined, page_size: 50 } });
  items.value = data.data.items || [];
}

async function create() {
  await http.post("/users", form);
  ElMessage.success("已创建");
  dialog.value = false;
  form.username = "";
  form.email = "";
  form.password = "";
  form.role = "member";
  await load();
}

async function changeRole(row: UserRow, role: string) {
  await http.patch(`/users/${row.id}`, { role });
  ElMessage.success("角色已更新");
  await load();
}

async function toggleActive(row: UserRow) {
  await http.patch(`/users/${row.id}`, { is_active: !row.is_active });
  ElMessage.success(row.is_active ? "已禁用" : "已启用");
  await load();
}

onMounted(load);
</script>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.actions {
  display: flex;
  gap: 8px;
}
</style>
