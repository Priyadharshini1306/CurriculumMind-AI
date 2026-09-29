// Search-result titles sometimes arrive as several titles glued together; keep the first, readable part.
export const short = (s, n = 90) => {
  const t = (s ?? '').replace(/\s+/g, ' ').trim()
  return t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t
}
