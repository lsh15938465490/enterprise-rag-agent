/**
 * 页面路由表。
 * public: 不用登录（登录页）；requiresAdmin: 只有管理员能进用户管理。
 */
import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: () => import("../views/Login.vue"), meta: { public: true } },
    {
      path: "/",
      component: () => import("../layouts/MainLayout.vue"),
      children: [
        { path: "", redirect: "/chat" },
        { path: "chat", name: "chat", component: () => import("../views/Chat.vue") },
        { path: "chat/:conversationId", name: "chat-detail", component: () => import("../views/Chat.vue") },
        { path: "kbs", name: "kbs", component: () => import("../views/KnowledgeBases.vue") },
        { path: "kbs/:id/docs", name: "docs", component: () => import("../views/Documents.vue") },
        { path: "history", name: "history", component: () => import("../views/History.vue") },
        {
          path: "admin/users",
          name: "admin-users",
          component: () => import("../views/AdminUsers.vue"),
          meta: { requiresAdmin: true },
        },
      ],
    },
  ],
});

// 每次跳转前检查：没 token 去登录；过期就清会话；非管理员不能进后台。
router.beforeEach(async (to) => {
  const token = localStorage.getItem("access_token");
  const auth = useAuthStore();
  if (!to.meta.public && !token) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
  if (to.path === "/login" && token) {
    return { path: "/chat" };
  }
  if (token && !auth.user) {
    try {
      await auth.loadMe();
    } catch {
      auth.logout();
      return { path: "/login" };
    }
  }
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { path: "/chat" };
  }
  return true;
});

export default router;
