const jsonHeaders = { "content-type": "application/json" };

async function request(path, init) {
  const res = await fetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}

export const api = {
  health: () => request("/api/health"),
  categories: () => request("/api/categories"),
  browse: ({ category, page, sort }) =>
    request(`/api/browse?category=${encodeURIComponent(category)}&page=${page}&sort=${sort}`),
  search: ({ q, page, sort }) =>
    request(`/api/search?q=${encodeURIComponent(q)}&page=${page}&sort=${sort}`),
  skill: (slug) => request(`/api/skill/${encodeURIComponent(slug)}`),
  install: ({ slug, quiet }) =>
    request("/api/install", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ slug, quiet }),
    }),
  installed: () => request("/api/installed"),
};

export function compact(n) {
  if (!n) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(n);
}

export function timeAgo(iso) {
  if (!iso) return "";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
}
