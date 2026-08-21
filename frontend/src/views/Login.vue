<template>
  <!-- 登录页：用户名 + 密码，成功后跳转问答 -->
  <div class="login-wrap">
    <el-card class="card">
      <template #header>
        <div class="card-title">
          <span>登录</span>
          <span class="hint">（用户名：admin 登录密码：Admin@123456）</span>
        </div>
      </template>
      <el-form label-position="top" @submit.prevent="onSubmit">
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
// 登录表单。密码不要写死在页面里，由使用者自己输入。
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const loading = ref(false);
const form = reactive({
  username: "",
  password: "",
});

async function onSubmit() {
  // 提交登录表单。租户固定走演示租户 demo，页面不再填写。
  if (!form.username || !form.password) {
    ElMessage.warning("请填写用户名和密码");
    return;
  }
  loading.value = true;
  try {
    await auth.login(form.username, form.password);
    ElMessage.success("登录成功");
    router.push("/chat");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100%;
  display: grid;
  place-items: center;
  background: #f5f7fa;
}
.card {
  width: 420px;
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
