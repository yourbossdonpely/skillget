// TypingMind catalog + detail client, ported from tools/tm_catalog.py.

export const BASE = "https://www.typingmind.com";
export const FALLBACK_BUILD = "build-TfctsWXpff2fKS";
export const PAGE_SIZE = 51;
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** GET with bounded exponential backoff. Throws on network failure. */
export async function request(url, { tries = 4, timeout = 45 } = {}) {
  let lastError;
  for (let attempt = 0; attempt < tries; attempt += 1) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout * 1000);
    try {
      const res = await fetch(url, {
        redirect: "follow",
        signal: ctrl.signal,
        headers: {
          "user-agent": UA,
          accept: "application/json,text/html;q=0.9,*/*;q=0.8",
        },
      });
      if ([429, 500, 502, 503, 504].includes(res.status)) {
        lastError = new Error(`HTTP ${res.status} for ${url}`);
        await sleep((2 ** attempt) * 1000 + Math.random() * 1000);
        continue;
      }
      return res;
    } catch (err) {
      lastError = err;
      await sleep((2 ** attempt) * 1000 + Math.random() * 1000);
    } finally {
      clearTimeout(timer);
    }
  }
  throw lastError ?? new Error(`request failed: ${url}`);
}

/** Regex the buildId out of the page HTML, falling back to the pinned build. */
export async function discoverBuildId() {
  try {
    const res = await request(`${BASE}/skills?category=devops`, { tries: 2 });
    if (res.status === 200) {
      const m = (await res.text()).match(/"buildId":"([^"]+)"/);
      if (m) return { buildId: m[1], fallback: false };
    }
  } catch {
    /* fall through to the pinned build */
  }
  return { buildId: FALLBACK_BUILD, fallback: true };
}

function unwrap(data) {
  const props = data?.props ?? data;
  const json = props?.pageProps?.json;
  if (!json) throw new Error("unexpected payload: no pageProps.json");
  return json;
}

export function toSkill(row) {
  return {
    id: String(row.id ?? ""),
    slug: row.slug ?? "",
    name: row.name ?? "",
    description: row.description ?? "",
    owner: row.owner ?? "",
    stars: Number(row.stars) || 0,
    resourcesCount: Number(row.resourcesCount) || 0,
    isPopular: Boolean(row.isPopular),
  };
}

/** One list page (category, optional q/author filters). */
export async function fetchPageProps({ category, page = 1, sort = "stars", build, extra = {} }) {
  const params = new URLSearchParams({ category, page: String(page), sort, ...extra });
  const url = `${BASE}/_next/data/${encodeURIComponent(build)}/skills.json?${params}`;
  let lastError = "unknown";
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      const res = await request(url);
      if (res.status === 200) {
        const json = unwrap(await res.json());
        return {
          initialPage: Number(json.initialPage) || page,
          skills: Array.isArray(json.skills) ? json.skills : [],
          totalCount: Number(json.totalCount) || 0,
        };
      }
      lastError = `HTTP ${res.status}`;
    } catch (err) {
      lastError = err.message;
    }
    await sleep(1500 * (attempt + 1));
  }
  throw new Error(`catalog page ${page} failed: ${lastError}`);
}

/** One category page, deduped — the Browse screen's data. */
export async function listCategory({ category, sort = "stars", page = 1, build }) {
  const props = await fetchPageProps({ category, page, sort, build });
  return {
    category,
    sort,
    page: props.initialPage,
    totalCount: props.totalCount,
    skills: dedupe(props.skills),
  };
}

/** Site search (TypingMind only), one page at a time. */
export async function searchSkills({ q, category = "all", sort = "stars", page = 1, build }) {
  const props = await fetchPageProps({ category, page, sort, build, extra: { q } });
  return {
    q,
    category,
    sort,
    page,
    totalCount: props.totalCount,
    skills: dedupe(props.skills),
  };
}

function dedupe(rows) {
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    if (!row?.slug || seen.has(row.slug)) continue;
    seen.add(row.slug);
    out.push(toSkill(row));
  }
  return out;
}

/** Full detail payload for one skill (sourceURL, path, branch, resources, bodyMarkdown). */
export async function fetchDetail(slug, build) {
  const url = `${BASE}/_next/data/${encodeURIComponent(build)}/skills/${encodeURIComponent(slug)}.json`;
  let lastError = "unknown";
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const res = await request(url, { tries: 3 });
      if (res.status === 404) {
        const err = new Error(`skill not found: ${slug}`);
        err.code = "NOT_FOUND";
        throw err;
      }
      if (res.status === 200) {
        const json = unwrap(await res.json());
        if (!json.skill) throw new Error("unexpected payload: no skill");
        return json.skill;
      }
      lastError = `HTTP ${res.status}`;
    } catch (err) {
      if (err.code === "NOT_FOUND") throw err;
      lastError = err.message;
    }
    await sleep(1500 * (attempt + 1));
  }
  throw new Error(lastError);
}
