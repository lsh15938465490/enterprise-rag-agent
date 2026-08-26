/**
 * 登录态按浏览器标签页隔离（sessionStorage）。
 * 同一浏览器两个标签可分别登录不同账号，互不覆盖。
 */
const ACCESS = "access_token";
const REFRESH = "refresh_token";
const USER = "auth_user";

function takeLocal(key: string): string | null {
  const v = localStorage.getItem(key);
  if (v) localStorage.removeItem(key);
  return v;
}

/** 把旧版 localStorage 登录态迁到当前标签，并清掉共享存储，避免多标签串号。 */
function adoptLegacyLocalAuth() {
  if (sessionStorage.getItem(ACCESS)) {
    localStorage.removeItem(ACCESS);
    localStorage.removeItem(REFRESH);
    localStorage.removeItem(USER);
    return;
  }
  const access = takeLocal(ACCESS);
  if (!access) return;
  sessionStorage.setItem(ACCESS, access);
  const refresh = takeLocal(REFRESH);
  if (refresh) sessionStorage.setItem(REFRESH, refresh);
  const user = takeLocal(USER);
  if (user) sessionStorage.setItem(USER, user);
}

adoptLegacyLocalAuth();

export function getAccessToken(): string {
  return sessionStorage.getItem(ACCESS) || "";
}

export function getRefreshToken(): string {
  return sessionStorage.getItem(REFRESH) || "";
}

export function getStoredUserRaw(): string | null {
  return sessionStorage.getItem(USER);
}

export function setAuthTokens(access: string, refresh: string) {
  sessionStorage.setItem(ACCESS, access);
  sessionStorage.setItem(REFRESH, refresh);
}

export function setStoredUserRaw(raw: string) {
  sessionStorage.setItem(USER, raw);
}

export function clearAuthStorage() {
  sessionStorage.removeItem(ACCESS);
  sessionStorage.removeItem(REFRESH);
  sessionStorage.removeItem(USER);
  localStorage.removeItem(ACCESS);
  localStorage.removeItem(REFRESH);
  localStorage.removeItem(USER);
}
