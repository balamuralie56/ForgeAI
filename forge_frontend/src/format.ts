/**
 * Turns any report value into displayable text. Local models sometimes return
 * an object (e.g. `{ "type": "integer", "description": "..." }`) where the
 * report schema promises a string; rendering that object directly would crash
 * React, so every free-text field goes through here.
 */
export function toText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record.type === "string") {
      const description = typeof record.description === "string" ? record.description : "";
      return description ? `${record.type} — ${description}` : record.type;
    }
    return JSON.stringify(value);
  }
  return String(value);
}
