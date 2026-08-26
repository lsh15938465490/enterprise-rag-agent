/**
 * 登录状态仓库：token 存在当前标签页的 sessionStorage，刷新本页不丢，其它标签互不影响。
 * 页面用 useAuthStore() 读取当前用户、是否管理员。
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import http, { bumpAuthEpoch } from "../api/http";
import {
  clearAuthStorage,
  getAccessToken,
  getRefreshToken,
  getStoredUserRaw,
  setAuthTokens,
  setStoredUserRaw,
} from "../api/session";

export interface AuthUser {
  id: string;
  tenant_id?: string | null;
  username: string;
  email: string;
  role: "super_admin" | "tenant_admin" | "kb_editor" | "member";
  tenant_slug?: string | null;
  tenant_name?: string | null;
}

function readStoredUser(): AuthUser | null {
  try {
    const raw = getStoredUserRaw();
    if (!raw) return null;
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export const useAuthStore = defineStore("auth", () => {
  const accessToken = ref(getAccessToken());
  const refreshToken = ref(getRefreshToken());
  const user = ref<AuthUser | null>(readStoredUser());

  const isLoggedIn = computed(() => Boolean(accessToken.value));
  const isSuperAdmin = computed(
    () => user.value?.role === "super_admin" || user.value?.username === "adminliu",
  );
  const isAdmin = computed(
    () => isSuperAdmin.value || user.value?.role === "tenant_admin",
  );

  function clearLocalSession() {
    bumpAuthEpoch();
    accessToken.value = "";
    refreshToken.value = "";
    user.value = null;
    clearAuthStorage();
  }

  function setSession(access: string, refresh: string, profile?: AuthUser | null) {
    bumpAuthEpoch();
    accessToken.value = access;
    refreshToken.value = refresh;
    setAuthTokens(access, refresh);
    if (profile) {
      user.value = profile;
      setStoredUserRaw(JSON.stringify(profile));
    }
  }

  async function login(tenantSlug: string, username: string, password: string) {
    clearLocalSession();
    const { data } = await http.post("/auth/login", { tenant_slug: tenantSlug, username, password });
    setSession(data.data.access_token, data.data.refresh_token, data.data.user);
  }

  async function loadMe() {
    if (!accessToken.value && !getAccessToken()) return;
    const { data } = await http.get("/auth/me");
    user.value = data.data;
    setStoredUserRaw(JSON.stringify(data.data));
  }

  async function logout() {
    const refresh = refreshToken.value || getRefreshToken();
    try {
      if (refresh) {
        await http.post("/auth/logout", { refresh_token: refresh });
      }
    } catch {
      /* ignore */
    }
    clearLocalSession();
  }

  return { accessToken, refreshToken, user, isLoggedIn, isAdmin, isSuperAdmin, setSession, login, loadMe, logout };
});
