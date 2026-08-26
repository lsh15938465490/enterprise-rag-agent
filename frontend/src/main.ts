/**
 * 前端入口：创建 Vue 应用，挂上路由、状态仓库、Element Plus 组件库。
 * index.html 里的 #app 就是页面最终渲染的地方。
 */
import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import "./api/session";
import App from "./App.vue";
import router from "./router";
import "./style.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.use(ElementPlus);
app.mount("#app");
