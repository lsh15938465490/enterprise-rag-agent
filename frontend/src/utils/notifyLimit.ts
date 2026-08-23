/**
 * 超限时弹出提示，3 秒后自动关闭。
 */
import { ElNotification } from "element-plus";

export function notifyLimit(message: string, title = "无法新建") {
  ElNotification({
    title,
    message,
    type: "warning",
    duration: 3000,
  });
}
