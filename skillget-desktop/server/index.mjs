// skillget-desktop local server: TypingMind browse/search/detail/install + Vite UI.
import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";
import {
  discoverBuildId,
  fetchDetail,
  fetchPageProps,
  listCategory,
  searchSkills,
} from "./engine/catalog.mjs";
import { installSkill } from "./engine/installer.mjs";
import { Manifest, pickFolder } from "./engine/manifest.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const DEST = path.resolve(process.env.SKILLGET_DEST || path.join(os.homedir(), ".agents", "skills"));
const STATE = path.resolve(process.env.SKILLGET_STATE || path.join(ROOT, ".state"));
const FRONTEND = path.resolve(process.env.SKILLGET_FRONTEND || path.join(ROOT, "dist"));
const MANIFEST_PATH = path.join(STATE, "manifest.json");
const PORT = Number(process.env.SKILLGET_PORT) || 5179;
const PROD = process.argv.includes("--prod");

// TypingMind's own category slugs. The site renders these client-side, so the
// list is declared here and each count is read live from the catalog endpoint.
const CATEGORIES = [
  ["software-development", "Software Development"],
  ["devops", "DevOps"],
  ["ai-ml", "AI & ML"],
  ["security", "Security"],
  ["productivity", "Productivity"],
  ["design", "Design"],
  ["data-analysis", "Data Analysis"],
  ["business-finance", "Business & Finance"],
  ["testing-qa", "Testing & QA"],
  ["media", "Media"],
  ["writing", "Writing"],
  ["research", "Research"],
  ["marketing", "Marketing"],
  ["document-processing", "Document Processing"],
  ["communication", "Communication"],
  ["education", "Education"],
];

let buildCache = { value: null, at: 0 };

async function buildId({ refresh = false } = {}) {
  if (!refresh && buildCache.value && Date.now() - buildCache.at < 15 * 60_000) {
    return buildCache.value;
  }
  const found = await discoverBuildId();
  buildCache = { value: found.buildId, at: Date.now() };
  return found.buildId;
}

/** Retry once with a freshly discovered buildId when Next.js rotated it. */
async function withBuild(fn, retried = false) {
  try {
    return await fn(await buildId({ refresh: retried }));
  } catch (err) {
    if (!retried && /404/.test(String(err.message))) return withBuild(fn, true);
    throw err;
  }
}

let categoryCache = { at: 0, data: null };

async function mapLimit(items, limit, fn) {
  const out = new Array(items.length);
  let cursor = 0;
  await Promise.all(
    Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (cursor < items.length) {
        const i = cursor;
        cursor += 1;
        out[i] = await fn(items[i], i);
      }
    }),
  );
  return out;
}

async function categories() {
  if (categoryCache.data && Date.now() - categoryCache.at < 10 * 60_000) return categoryCache.data;
  const build = await buildId();
  const rows = await mapLimit(CATEGORIES, 6, async ([slug, label]) => {
    try {
      const props = await fetchPageProps({ category: slug, build });
      return { slug, label, count: props.totalCount };
    } catch {
      return { slug, label, count: null };
    }
  });
  const data = rows.sort((a, b) => (b.count ?? -1) - (a.count ?? -1));
  categoryCache = { at: Date.now(), data };
  return data;
}

async function libraryFolders() {
  try {
    const entries = await fs.readdir(DEST, { withFileTypes: true });
    return entries.filter((e) => e.isDirectory() && !e.name.startsWith(".")).length;
  } catch {
    return 0;
  }
}

function shapeDetail(skill) {
  return {
    slug: skill.slug ?? "",
    name: skill.name ?? skill.slug ?? "",
    description: skill.description ?? skill.shortDescription ?? "",
    owner: skill.owner ?? "",
    stars: Number(skill.stars) || 0,
    license: skill.license ?? "",
    compatibility: skill.compatibility ?? "",
    categories: skill.categories ?? [],
    sourceURL: skill.sourceURL ?? "",
    githubUrl: skill.githubUrl ?? "",
    repoPath: skill.path ?? "",
    branch: skill.defaultBranch ?? "",
    resources: (Array.isArray(skill.resources) ? skill.resources : []).map((r) => ({
      path: String(r?.path ?? ""),
      type: String(r?.type ?? ""),
    })),
    bodyMarkdown: String(skill.bodyMarkdown ?? "").slice(0, 20000),
  };
}

async function installedInfo(slug) {
  const manifest = await Manifest.load(MANIFEST_PATH);
  const entry = manifest.get(slug);
  if (!entry?.folder) return { installed: false };
  let onDisk = false;
  let skillMdBytes = 0;
  try {
    const stat = await fs.stat(path.join(DEST, entry.folder, "SKILL.md"));
    onDisk = true;
    skillMdBytes = stat.size;
  } catch {
    /* folder vanished */
  }
  return {
    installed: onDisk,
    installedFolder: entry.folder,
    installedAt: entry.updated_at ?? entry.installed_at ?? "",
    installedQuiet: Boolean(entry.quiet),
    skillMdBytes,
  };
}

async function installedList() {
  const manifest = await Manifest.load(MANIFEST_PATH);
  const entries = Object.entries(manifest.data.skills);
  const rows = await mapLimit(entries, 8, async ([slug, entry]) => {
    let onDisk = false;
    let skillMdBytes = 0;
    let quiet = Boolean(entry.quiet);
    if (entry.folder) {
      try {
        const stat = await fs.stat(path.join(DEST, entry.folder, "SKILL.md"));
        onDisk = stat.size > 0;
        skillMdBytes = stat.size;
        const meta = JSON.parse(
          await fs.readFile(path.join(DEST, entry.folder, ".skillget.json"), "utf8"),
        );
        quiet = Boolean(meta.quiet);
      } catch {
        /* missing or unreadable provenance counts as not on disk */
      }
    }
    return {
      slug,
      name: entry.name ?? slug,
      folder: entry.folder ?? "",
      status: entry.status ?? "unknown",
      source: entry.source ?? "",
      skillMd: entry.skill_md ?? "",
      files: entry.files ?? 0,
      quiet,
      onDisk,
      skillMdBytes,
      installedAt: entry.updated_at ?? entry.installed_at ?? "",
      error: entry.error ?? "",
    };
  });
  rows.sort((a, b) => String(b.installedAt).localeCompare(String(a.installedAt)));
  return {
    dest: DEST,
    libraryFolders: await libraryFolders(),
    tracked: rows.length,
    healthy: rows.filter((r) => r.onDisk).length,
    quiet: rows.filter((r) => r.quiet).length,
    rows,
  };
}

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  res.end(payload);
}

async function readBody(req) {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  if (!raw) return {};
  return JSON.parse(raw);
}

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".woff2": "font/woff2",
};

async function serveStatic(req, res) {
  const url = new URL(req.url, "http://localhost");
  let filePath = path.join(FRONTEND, decodeURIComponent(url.pathname));
  if (!path.resolve(filePath).startsWith(FRONTEND)) filePath = path.join(FRONTEND, "index.html");
  try {
    const stat = await fs.stat(filePath);
    if (stat.isDirectory()) filePath = path.join(filePath, "index.html");
  } catch {
    filePath = path.join(FRONTEND, "index.html");
  }
  try {
    const data = await fs.readFile(filePath);
    res.writeHead(200, { "content-type": MIME[path.extname(filePath)] ?? "application/octet-stream" });
    res.end(data);
  } catch {
    res.writeHead(404).end("run `npm run build` first");
  }
}

async function handleApi(req, res, url) {
  const route = url.pathname;

  if (req.method === "GET" && route === "/api/health") {
    const manifest = await Manifest.load(MANIFEST_PATH);
    return sendJson(res, 200, {
      dest: DEST,
      manifest: MANIFEST_PATH,
      buildId: await buildId(),
      libraryFolders: await libraryFolders(),
      tracked: Object.keys(manifest.data.skills).length,
    });
  }

  if (req.method === "GET" && route === "/api/categories") {
    return sendJson(res, 200, { categories: await categories() });
  }

  if (req.method === "GET" && route === "/api/browse") {
    const category = url.searchParams.get("category") || "software-development";
    const page = Math.max(1, Number(url.searchParams.get("page")) || 1);
    const sort = url.searchParams.get("sort") || "stars";
    const data = await withBuild((build) => listCategory({ category, page, sort, build }));
    return sendJson(res, 200, { ...data, buildId: buildCache.value });
  }

  if (req.method === "GET" && route === "/api/search") {
    const q = (url.searchParams.get("q") || "").trim();
    if (q.length < 2) return sendJson(res, 400, { error: "query needs at least 2 characters" });
    const page = Math.max(1, Number(url.searchParams.get("page")) || 1);
    const sort = url.searchParams.get("sort") || "stars";
    const data = await withBuild((build) => searchSkills({ q, page, sort, build }));
    return sendJson(res, 200, data);
  }

  const detailMatch = route.match(/^\/api\/skill\/([^/]+)$/);
  if (req.method === "GET" && detailMatch) {
    const slug = decodeURIComponent(detailMatch[1]);
    try {
      const detail = await withBuild((build) => fetchDetail(slug, build));
      return sendJson(res, 200, {
        skill: shapeDetail(detail),
        ...(await installedInfo(slug)),
      });
    } catch (err) {
      const status = err.code === "NOT_FOUND" ? 404 : 502;
      return sendJson(res, status, { error: err.message });
    }
  }

  if (req.method === "POST" && route === "/api/install") {
    const body = await readBody(req);
    const slug = String(body.slug ?? "").trim();
    if (!slug) return sendJson(res, 400, { error: "slug is required" });
    const quiet = body.quiet !== false;
    let detail;
    try {
      detail = await withBuild((build) => fetchDetail(slug, build));
    } catch (err) {
      const status = err.code === "NOT_FOUND" ? 404 : 502;
      return sendJson(res, status, { error: err.message });
    }
    const manifest = await Manifest.load(MANIFEST_PATH);
    const owned = new Set(
      Object.values(manifest.data.skills)
        .map((e) => e.folder)
        .filter(Boolean),
    );
    const folder = await pickFolder(DEST, slug, manifest, owned);
    const result = await installSkill(detail, DEST, { folder, quiet });
    if (result.status !== "ok") {
      manifest.mark(slug, { status: "error", error: result.error, folder: result.folder });
      await manifest.save();
      return sendJson(res, 500, { error: result.error, ...result });
    }
    manifest.mark(slug, {
      status: "ok",
      folder: result.folder,
      name: result.name,
      source: result.source,
      license: result.license,
      categories: result.categories,
      skill_md: result.skillMd,
      files: result.files,
      quiet: result.quiet,
    });
    await manifest.save();
    return sendJson(res, 200, { ok: true, ...result });
  }

  if (req.method === "GET" && route === "/api/installed") {
    return sendJson(res, 200, await installedList());
  }

  return sendJson(res, 404, { error: `no route: ${req.method} ${route}` });
}

async function main() {
  let vite = null;
  if (!PROD) {
    const { createServer } = await import("vite");
    vite = await createServer({ root: ROOT, server: { middlewareMode: true }, appType: "spa" });
  }

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    try {
      if (url.pathname.startsWith("/api/")) {
        await handleApi(req, res, url);
        return;
      }
      if (vite) {
        vite.middlewares(req, res, (err) => {
          if (err) {
            res.writeHead(500).end(String(err));
          }
        });
        return;
      }
      await serveStatic(req, res);
    } catch (err) {
      console.error(`[api] ${req.method} ${url.pathname}:`, err);
      if (!res.headersSent) sendJson(res, 500, { error: err.message });
    }
  });

  server.listen(PORT, "127.0.0.1", () => {
    console.log(`skillget-desktop on http://127.0.0.1:${PORT}`);
    console.log(`destination: ${DEST}`);
    console.log(`state: ${MANIFEST_PATH}`);
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
