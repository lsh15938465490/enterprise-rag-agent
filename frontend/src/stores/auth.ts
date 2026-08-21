/**
 * 登录状态仓库：token 存在浏览器 localStorage，刷新页面也不会丢。
 * 页面用 useAuthStore() 读取当前用户、是否管理员。
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import http from "../api/http";

export interface AuthUser {
  id: string;
  tenant_id: string;
  username: string;
  email: string;
  role: "super_admin" | "tenant_admin" | "kb_editor" | "member";
}

export const useAuthStore = defineStore("auth", () => {
  const accessToken = ref(localStorage.getItem("access_token") || "");
  const refreshToken = ref(localStorage.getItem("refresh_token") || "");
  const user = ref<AuthUser | null>(null);

  const isLoggedIn = computed(() => Boolean(accessToken.value));
  const isAdmin = computed(
    () => user.value?.role === "tenant_admin" || user.value?.role === "super_admin",
  );

  function setSession(access: string, refresh: string, profile?: AuthUser) {
    // 同时写入内存和 localStorage，刷新页面还能保持登录
    accessToken.value = access;
    refreshToken.value = refresh;
    localStorage.setItem("access_token", access);
    localStorage.setItem("refresh_token", refresh);
    if (profile) {
      user.value = profile;
    }
  }

  async function login(username: string, password: string) {
    // 调后端 /auth/login。单租户界面固定 demo，不再让用户填 slug。
    const { data } = await http.post("/auth/login", { tenant_slug: "demo", username, password });
    setSession(data.data.access_token, data.data.refresh_token, data.data.user);
  }

  async function loadMe() {
    // 用 access token 拉当前用户，给路由判断管理员
    if (!accessToken.value) return;
    const { data } = await http.get("/auth/me");
    user.value = data.data;
  }

  async function logout() {
    // 先通知后端拉黑 refresh，再清本地
    const refresh = refreshToken.value;
    try {
      if (refresh) {
        await http.post("/auth/logout", { refresh_token: refresh });
      }
    } catch {
      /* ignore */
    }
    accessToken.value = "";
    refreshToken.value = "";
    user.value = null;
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  }

  return { accessToken, refreshToken, user, isLoggedIn, isAdmin, setSession, login, loadMe, logout };
});
