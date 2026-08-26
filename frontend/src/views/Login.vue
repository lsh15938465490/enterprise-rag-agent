<template>
  <!-- 登录页：租户 + 用户名 + 密码 -->
  <div class="login-wrap">
    <el-card class="card">
      <template #header>
        <div class="card-title">
          <span>登录</span>
          <span class="hint">（部门01：admin01 / user01；部门02：admin02 / user02。密码均为 Admin@123456）</span>
        </div>
      </template>
      <el-form label-position="top" @submit.prevent="onSubmit">
        <el-form-item label="部门">
          <el-select v-model="form.tenant_slug" placeholder="请选择部门" style="width: 100%" filterable>
            <el-option v-for="t in tenants" :key="t.slug" :label="t.name" :value="t.slug" />
          </el-select>
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-button type="primary" native-type="submit" style="width: 100%" :loading="loading">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import http from "../api/http";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const loading = ref(false);
const tenants = ref<{ slug: string; name: string }[]>([]);
const form = reactive({
  tenant_slug: "",
  username: "",
  password: "",
});

function safeRedirect(): string {
  const raw = route.query.redirect;
  if (typeof raw !== "string") return "/chat";
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/login")) return "/chat";
  return raw;
}

async function loadTenants() {
  const { data } = await http.get("/auth/tenants");
  tenants.value = data.data || [];
  if (!tenants.value.some((t) => t.slug === form.tenant_slug) && tenants.value[0]) {
    form.tenant_slug = tenants.value[0].slug;
  }
}

async function onSubmit() {
  if (!form.tenant_slug) {
    ElMessage.warning("请选择部门");
    return;
  }
  if (!form.username || !form.password) {
    ElMessage.warning("请填写用户名和密码");
    return;
  }
  loading.value = true;
  try {
    await auth.login(form.tenant_slug, form.username, form.password);
    ElMessage.success("登录成功");
    router.push(safeRedirect());
  } finally {
    loading.value = false;
  }
}

onMounted(loadTenants);
</script>

<style scoped>
.login-wrap {
  height: 100%;
  display: grid;
  place-items: center;
  background: #f5f7fa;
}
.card {
  width: 520px;
}
.card-title {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px;
}
.hint {
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}
</style>
