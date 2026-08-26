/**
 * 调用后端的统一入口。
 * 自动带上 JWT；业务 code 不为 0 会弹错误；401 会尝试用 refresh_token 换新令牌。
 */
import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { ElMessage } from "element-plus";
import { clearAuthStorage, getAccessToken, getRefreshToken, setAuthTokens } from "./session";

export interface Envelope<T> {
  code: number;
  message: string;
  data: T;
  request_id: string;
}

const http = axios.create({
  baseURL: "/api/v1",
  timeout: 60000,
});

/** 切换账号时加 1，作废进行中的 refresh，避免把上一用户的 token 写回来。 */
let authEpoch = 0;

export function bumpAuthEpoch() {
  authEpoch += 1;
}

function isAuthUrl(url?: string) {
  const u = url || "";
  return u.includes("/auth/login") || u.includes("/auth/refresh") || u.includes("/auth/logout") || u.includes("/auth/tenants");
}

http.interceptors.request.use((config) => {
  if (isAuthUrl(config.url)) {
    return config;
  }
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshing = false;

http.interceptors.response.use(
  (res) => {
    if (res.headers["content-type"]?.includes("text/event-stream")) {
      return res;
    }
    const body = res.data as Envelope<unknown>;
    if (body && typeof body.code === "number" && body.code !== 0) {
      ElMessage.error(body.message || "请求失败");
      return Promise.reject(body);
    }
    return res;
  },
  async (err: AxiosError<Envelope<unknown>>) => {
    const original = err.config as InternalAxiosRequestConfig & { _retry?: boolean; _epoch?: number };
    if (err.response?.status === 401 && original && !original._retry && !isAuthUrl(original.url)) {
      original._retry = true;
      const epochAtFail = authEpoch;
      const sent = String(original.headers?.Authorization || "");
      const current = getAccessToken();
      if (sent && current && sent !== `Bearer ${current}`) {
        return Promise.reject(err);
      }
      const refresh = getRefreshToken();
      if (refresh && !refreshing) {
        refreshing = true;
        try {
          const resp = await axios.post<Envelope<{ access_token: string; refresh_token: string }>>(
            "/api/v1/auth/refresh",
            { refresh_token: refresh },
          );
          if (epochAtFail !== authEpoch) {
            return Promise.reject(err);
          }
          const data = resp.data.data;
          setAuthTokens(data.access_token, data.refresh_token);
          original.headers = original.headers || {};
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return http(original);
        } catch {
          if (epochAtFail === authEpoch) {
            clearAuthStorage();
            window.location.href = "/login";
          }
        } finally {
          refreshing = false;
        }
      } else if (!refresh) {
        window.location.href = "/login";
      }
    }
    const msg = err.response?.data?.message || err.message;
    if (msg && !isAuthUrl(original?.url) ) {
      ElMessage.error(msg);
    } else if (msg && original?.url?.includes("/auth/login")) {
      ElMessage.error(msg);
    }
    return Promise.reject(err);
  },
);

export default http;
