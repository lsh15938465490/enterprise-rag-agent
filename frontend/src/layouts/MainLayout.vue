<template>
  <!-- 登录后的外壳：左侧菜单 + 顶栏用户名 + 中间是具体页面 -->
  <el-container class="shell">
    <el-aside width="220px" class="aside">
      <div class="brand">企业知识库问答</div>
      <el-menu :router="true" :default-active="route.path">
        <el-menu-item index="/chat">智能问答</el-menu-item>
        <el-menu-item index="/kbs">知识库</el-menu-item>
        <el-menu-item index="/history">历史会话</el-menu-item>
        <el-menu-item v-if="auth.isAdmin" index="/stats">数据统计</el-menu-item>
        <el-menu-item v-if="auth.isAdmin" index="/admin/users">权限管理</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span>RAG 问答</span>
        <span>
          {{ auth.user?.username }}
          <el-tag v-if="auth.user?.tenant_name || auth.user?.tenant_slug" size="small" style="margin: 0 8px">
            {{ auth.user.tenant_name || auth.user.tenant_slug }}
          </el-tag>
          <el-tag v-if="auth.user" size="small" :type="auth.isAdmin ? 'warning' : 'info'" style="margin: 0 8px">
            {{ roleLabel }}
          </el-tag>
          <el-button type="primary" link @click="logout">退出</el-button>
        </span>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
// 顶栏退出、侧栏根据是否管理员显示「用户管理」
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const roleLabel = computed(() => {
  if (auth.isSuperAdmin) return "超级管理员";
  if (auth.user?.role === "tenant_admin" || auth.isAdmin) return "管理者";
  return "普通用户";
});

onMounted(() => {
  auth.loadMe().catch(() => undefined);
});

async function logout() {
  await auth.logout();
  router.push("/login");
}
</script>

<style scoped>
.shell {
  height: 100%;
}
.aside {
  border-right: 1px solid #ebeef5;
}
.brand {
  padding: 20px 16px;
  font-weight: 600;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #ebeef5;
}
</style>
