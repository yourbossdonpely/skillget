// raw.githubusercontent.com download helpers, ported from tools/github_fetch.py.
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";

const RAW = "https://raw.githubusercontent.com";
const WINDOWS_ILLEGAL = /[<>:"|?*\x00-\x1f]/g;
const WINDOWS_RESERVED = new Set([
  "con",
  "prn",
  "aux",
  "nul",
  ...Array.from({ length: 9 }, (_, i) => `com${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `lpt${i + 1}`),
]);

/** Make one path segment writable on Windows (and anywhere else). */
export function safePart(name) {
  let out = String(name).replace(/\\/g, "_").replace(WINDOWS_ILLEGAL, "_");
  out = out.replace(/[ .]+$/, "") || "_";
  const stem = out.split(".")[0].toLowerCase();
  if (WINDOWS_RESERVED.has(stem)) out = `_${out}`;
  if (out.length > 120) {
    const dot = out.lastIndexOf(".");
    const ext = dot > 0 ? out.slice(dot + 1) : "";
    out = dot > 0 && ext.length <= 10 ? `${out.slice(0, 120 - ext.length - 1)}.${ext}` : out.slice(0, 120);
  }
  return out;
}

/** Repository-relative path -> safe segment list (null when unsafe). */
export function cleanRelPath(p) {
  if (!p) return null;
  const s = String(p).replace(/\\/g, "/").trim();
  if (s.startsWith("/") || /^[A-Za-z]:/.test(s)) return null;
  const rawParts = s.split("/");
  if (rawParts.some((part) => part === "..")) return null;
  const parts = rawParts.filter((x) => x !== "" && x !== ".");
  if (!parts.length) return null;
  return parts.map(safePart);
}

/** (owner, repo, branch, path) from detail metadata, sourceURL winning where set. */
export function parseSource(skill) {
  let owner = String(skill?.owner ?? "").trim();
  let repo = String(skill?.repo ?? "").trim();
  let branch = String(skill?.defaultBranch ?? "").trim();
  let skillPath = String(skill?.path ?? "").trim().replace(/^\/+|\/+$/g, "");
  const source = String(skill?.sourceURL ?? "").trim();
  if (source) {
    const m = source.match(
      /https?:\/\/github\.com\/([^/]+)\/([^/]+)(?:\/(?:tree|blob)\/([^/]+)(?:\/(.*))?)?/,
    );
    if (m) {
      owner = owner || m[1];
      repo = repo || m[2];
      branch = branch || (m[3] ?? "");
      skillPath = skillPath || (m[4] ?? "").replace(/^\/+|\/+$/g, "");
    }
  }
  if (!owner || !repo) return null;
  return { owner, repo, branch: branch || "HEAD", path: skillPath };
}

export function rawUrl(owner, repo, branch, relPath) {
  const encoded = relPath.split("/").map(encodeURIComponent).join("/");
  return `${RAW}/${owner}/${repo}/${encodeURIComponent(branch)}/${encoded}`;
}

/** Download bytes with a size cap. Returns {status, data}. */
async function getBytes(url, { maxBytes = 50 * 1024 * 1024, timeout = 60 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout * 1000);
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      redirect: "follow",
      headers: { "user-agent": "skillget-desktop" },
    });
    if (res.status !== 200) {
      await res.arrayBuffer().catch(() => {});
      return { status: res.status, data: null };
    }
    const declared = Number(res.headers.get("content-length") ?? 0);
    if (declared && declared > maxBytes) return { status: 413, data: null };
    const buf = Buffer.from(await res.arrayBuffer());
    if (buf.length > maxBytes) return { status: 413, data: null };
    return { status: 200, data: buf };
  } catch {
    return { status: 0, data: null };
  } finally {
    clearTimeout(timer);
  }
}

/** Canonical SKILL.md, same candidate order as the Python CLI. */
export async function fetchSkillMd(skill) {
  const src = parseSource(skill);
  if (!src) return { text: null, error: "no github source" };
  const candidates = [];
  if (src.path) candidates.push(`${src.path}/SKILL.md`, `${src.path}/skill.md`);
  candidates.push("SKILL.md");
  for (const rel of candidates) {
    const { status, data } = await getBytes(rawUrl(src.owner, src.repo, src.branch, rel), {
      maxBytes: 2 * 1024 * 1024,
    });
    if (status === 200 && data?.length) return { text: data.toString("utf8"), error: null };
  }
  return { text: null, error: "SKILL.md not found on raw.githubusercontent.com" };
}

/** Download every resource listed on the skill into destDir. */
export async function fetchResources(skill, destDir, { workers = 4 } = {}) {
  const resources = Array.isArray(skill?.resources) ? skill.resources : [];
  const src = parseSource(skill);
  if (!resources.length) return { written: [], failures: [] };
  if (!src) return { written: [], failures: [{ path: "", error: "no github source" }] };

  const written = [];
  const failures = [];
  let cursor = 0;

  const one = async (res) => {
    const relRaw = String(res?.path ?? "");
    const parts = cleanRelPath(relRaw);
    if (!parts) {
      failures.push({ path: relRaw, error: "unsafe path" });
      return;
    }
    const rel = parts.join("/");
    const full = src.path ? `${src.path}/${rel}` : rel;
    let got = await getBytes(rawUrl(src.owner, src.repo, src.branch, full));
    if (got.status !== 200 && src.path) {
      // Some payloads list paths relative to the repository root.
      got = await getBytes(rawUrl(src.owner, src.repo, src.branch, rel));
    }
    if (got.status !== 200 || !got.data) {
      failures.push({ path: relRaw, error: `HTTP ${got.status}` });
      return;
    }
    const target = join(destDir, ...parts);
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, got.data);
    written.push(rel);
  };

  await Promise.all(
    Array.from({ length: Math.max(1, Math.min(workers, resources.length)) }, async () => {
      while (cursor < resources.length) {
        const i = cursor;
        cursor += 1;
        await one(resources[i]);
      }
    }),
  );
  return { written, failures };
}
