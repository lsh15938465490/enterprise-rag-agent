/** 知识库切块若是 {'question':'...','answer':'...'}，界面只展示问题。 */
export function displayQuestion(text: string): string {
  const t = (text || "").trim();
  if (!t.startsWith("{") || !t.includes("question")) return t;
  try {
    const obj = JSON.parse(t);
    if (obj && typeof obj.question === "string" && obj.question.trim()) {
      return obj.question.trim();
    }
  } catch {
    /* Python 字典用单引号，走下面正则 */
  }
  const m = t.match(/['"]question['"]\s*:\s*['"]([^'"]+)['"]/);
  return m?.[1]?.trim() || t;
}
