/** 把助手回复里的 Markdown 转成安全 HTML（关闭原始 HTML，防止注入脚本）。 */
import MarkdownIt from "markdown-it";

const md = new MarkdownIt({ html: false, linkify: true, breaks: true });

export function renderMarkdown(source: string): string {
  return md.render(source || "");
}
