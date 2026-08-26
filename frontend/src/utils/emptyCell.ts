/** 表格空单元格统一占位。 */
export const EMPTY_CELL = "--";

export function cellText(value: unknown): string {
  if (value === null || value === undefined) return EMPTY_CELL;
  const text = String(value).trim();
  return text || EMPTY_CELL;
}
