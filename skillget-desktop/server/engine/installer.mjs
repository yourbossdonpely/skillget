// Atomic, never-clobbering install into a skills directory.
// Ported from tools/installer.py; quiet frontmatter is applied before the folder lands.
import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { fetchResources, fetchSkillMd, parseSource } from "./github.mjs";
import { ensureQuiet } from "./quiet.mjs";

const WINDOWS_RESERVED = new Set([
  "con",
  "prn",
  "aux",
  "nul",
  ...Array.from({ length: 9 }, (_, i) => `com${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `lpt${i + 1}`),
]);

export const utcNow = () => new Date().toISOString().replace(/\.\d+Z$/, "Z");

export function safeFolder(name) {
  let out = String(name || "skill").trim().toLowerCase();
  out = out.replace(/[^a-z0-9._-]+/g, "-").replace(/-{2,}/g, "-");
  out = out.replace(/^[-._]+|[-._]+$/g, "").slice(0, 100).replace(/[ .]+$/, "");
  if (!out) out = "skill";
  if (WINDOWS_RESERVED.has(out.toLowerCase())) out = `skill-${out}`;
  return out;
}

export function safeSkillName(name, fallback) {
  let out = String(name || fallback || "skill").trim().toLowerCase();
  out = out.replace(/[^a-z0-9-]+/g, "-").replace(/-{2,}/g, "-").replace(/^-+|-+$/g, "");
  return (out || "skill").slice(0, 64);
}

const yamlValue = (v) => JSON.stringify(String(v));

/** Same frontmatter the Python CLI synthesizes when raw SKILL.md is unavailable. */
export function synthesizeSkillMd(skill) {
  let body = String(skill?.bodyMarkdown ?? "").trim();
  if (!body) body = `# ${skill?.name ?? skill?.slug}\n\n${skill?.description ?? ""}\n`;
  const name = safeSkillName(skill?.skillName, skill?.slug);
  const desc = String(skill?.description ?? skill?.shortDescription ?? "")
    .trim()
    .replace(/\n/g, " ");
  const lines = ["---", `name: ${yamlValue(name)}`, `description: ${yamlValue(desc)}`];
  if (skill?.license) lines.push(`license: ${yamlValue(skill.license)}`);
  if (skill?.compatibility) lines.push(`compatibility: ${yamlValue(skill.compatibility)}`);
  if (Array.isArray(skill?.allowedTools) && skill.allowedTools.length) {
    lines.push(`allowed-tools: ${JSON.stringify(skill.allowedTools)}`);
  }
  if (skill?.metadata && Object.keys(skill.metadata).length) {
    lines.push(`metadata: ${JSON.stringify(skill.metadata)}`);
  }
  lines.push("---", "", body, "");
  return lines.join("\n");
}

/** True when a folder was installed by skillget for this slug (crash recovery). */
export async function folderBelongsTo(folderPath, slug) {
  try {
    return JSON.parse(await fs.readFile(path.join(folderPath, ".skillget.json"), "utf8"))?.slug === slug;
  } catch {
    return false;
  }
}

async function exists(p) {
  try {
    await fs.lstat(p);
    return true;
  } catch {
    return false;
  }
}

/** base, base-tm, base-tm-2, base-tm-3 ... */
function suffixed(base, n) {
  return n <= 1 ? base : n === 2 ? `${base}-tm` : `${base}-tm-${n - 1}`;
}

/**
 * Install one TypingMind detail payload.
 * Never overwrites a folder it does not own: a collision gets a `-tm` suffix.
 */
export async function installSkill(
  skill,
  dest,
  { folder, fetchMd = true, fetchFiles = true, resourceWorkers = 4, quiet = true } = {},
) {
  const slug = skill?.slug ?? "";
  const name = skill?.name ?? slug;
  const src = parseSource(skill);
  const source = skill?.sourceURL || (src ? `https://github.com/${src.owner}/${src.repo}` : "");
  let targetFolder = folder || safeFolder(slug);
  const result = {
    slug,
    name,
    folder: targetFolder,
    source,
    license: skill?.license ?? "",
    categories: skill?.categories ?? [],
    resourceFailures: [],
    skillMd: "generated",
    files: 0,
    quiet: false,
  };

  await fs.mkdir(dest, { recursive: true });
  const tmpRoot = path.join(dest, ".skillget-tmp");
  await fs.mkdir(tmpRoot, { recursive: true });
  const tmp = path.join(tmpRoot, `${targetFolder}-${crypto.randomBytes(4).toString("hex")}`);
  await fs.mkdir(tmp);

  try {
    let mdText = null;
    let mdError = null;
    if (fetchMd) ({ text: mdText, error: mdError } = await fetchSkillMd(skill));
    if (mdText) {
      result.skillMd = "raw";
    } else {
      mdText = synthesizeSkillMd(skill);
      result.skillMd = "generated";
      if (mdError) result.skillMdError = mdError;
    }
    if (!mdText.trim()) throw new Error("empty SKILL.md");

    if (quiet) {
      const q = ensureQuiet(mdText, name, skill?.description ?? "");
      mdText = q.text;
      result.quietStatus = q.status;
      result.quiet = ["added", "updated", "prepended", "already"].includes(q.status);
      if (q.status === "unparsed" || q.status === "unverified") result.quietError = q.status;
    }
    await fs.writeFile(path.join(tmp, "SKILL.md"), mdText, "utf8");
    result.files += 1;

    if (fetchFiles && Array.isArray(skill?.resources) && skill.resources.length) {
      const { written, failures } = await fetchResources(skill, tmp, { workers: resourceWorkers });
      result.files += written.length;
      result.resourceFailures = failures;
    }

    const provenance = {
      slug,
      name,
      source,
      github: skill?.githubUrl ?? "",
      license: skill?.license ?? "",
      categories: skill?.categories ?? [],
      installed_at: utcNow(),
      tool: "skillget",
      tool_version: "1.0.0",
      skill_md: result.skillMd,
      quiet: result.quiet,
      resources_failed: result.resourceFailures,
    };
    await fs.writeFile(
      path.join(tmp, ".skillget.json"),
      `${JSON.stringify(provenance, null, 2)}\n`,
      "utf8",
    );
    result.files += 1;

    let target = path.join(dest, targetFolder);
    if (await exists(target)) {
      if (await folderBelongsTo(target, slug)) {
        // Our own previous (possibly partial) install: replace in place.
        result.replacedExisting = true;
        await fs.rm(target, { recursive: true, force: true });
      } else {
        // Unowned folder (user skill or concurrent writer): never clobber.
        const base = targetFolder;
        let n = 1;
        while (await exists(target)) {
          n += 1;
          targetFolder = suffixed(base, n);
          target = path.join(dest, targetFolder);
        }
        result.folder = targetFolder;
      }
    }

    try {
      await fs.rename(tmp, target);
    } catch (err) {
      if (!["EEXIST", "EPERM", "ENOTEMPTY"].includes(err.code)) throw err;
      const base = targetFolder;
      let n = 1;
      while (await exists(target)) {
        n += 1;
        targetFolder = suffixed(base, n);
        target = path.join(dest, targetFolder);
      }
      result.folder = targetFolder;
      await fs.rename(tmp, target);
    }

    result.status = "ok";
    result.path = target;
    return result;
  } catch (err) {
    result.status = "error";
    result.error = `${err.name}: ${err.message}`;
    return result;
  } finally {
    await fs.rm(tmp, { recursive: true, force: true });
  }
}
