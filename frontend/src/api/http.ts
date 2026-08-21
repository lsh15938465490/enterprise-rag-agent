/**
 * 调用后端的统一入口。
 * 自动带上 JWT；业务 code 不为 0 会弹错误；401 会尝试用 refresh_token 换新令牌。
 */
import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { ElMessage } from "element-plus";

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

http.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
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
    const original = err.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (err.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      const refresh = localStorage.getItem("refresh_token");
      if (refresh && !refreshing) {
        refreshing = true;
        try {
          const resp = await axios.post<Envelope<{ access_token: string; refresh_token: string }>>(
            "/api/v1/auth/refresh",
            { refresh_token: refresh },
          );
          const data = resp.data.data;
          localStorage.setItem("access_token", data.access_token);
          localStorage.setItem("refresh_token", data.refresh_token);
          original.headers = original.headers || {};
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return http(original);
        } catch {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          window.location.href = "/login";
        } finally {
          refreshing = false;
        }
      } else if (!refresh) {
        window.location.href = "/login";
      }
    }
    const msg = err.response?.data?.message || err.message;
    ElMessage.error(msg);
    return Promise.reject(err);
  },
);

export default http;
