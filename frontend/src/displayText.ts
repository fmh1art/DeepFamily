export function sentenceCase(value: string): string {
  const normalized = value.replaceAll("_", " ");
  return normalized.length === 0
    ? normalized
    : `${normalized[0].toUpperCase()}${normalized.slice(1)}`;
}
