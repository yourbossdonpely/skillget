// Install-state manifest + non-destructive folder choice.
// Ported from tools/installer.py; the app keeps its own state file.
import fs from "node:fs/promises";
import path from "node:path";
import { folderBelongsTo, safeFolder, utcNow } from "./installer.mjs";

export class Manifest {
  constructor(file) {
    this.file = file;
    this.data = { version: 1, skills: {}, created_at: utcNow() };
  }

  static async load(file) {
    const m = new Manifest(file);
    try {
      const parsed = JSON.parse(await fs.readFile(file, "utf8"));
      m.data = { version: 1, skills: {}, created_at: utcNow(), ...parsed };
      m.data.skills ??= {};
    } catch {
      /* first run: keep the empty manifest */
    }
    return m;
  }

  get(slug) {
    return this.data.skills[slug] ?? null;
  }

  mark(slug, fields) {
    const entry = (this.data.skills[slug] ??= {});
    Object.assign(entry, fields);
    entry.updated_at = utcNow();
    return entry;
  }

  async save() {
    this.data.updated_at = utcNow();
    await fs.mkdir(path.dirname(this.file), { recursive: true });
    const tmp = `${this.file}.tmp`;
    await fs.writeFile(tmp, `${JSON.stringify(this.data, null, 2)}\n`, "utf8");
    await fs.rename(tmp, this.file);
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

/** Reuse our own recorded folder, otherwise suffix on collision. */
export async function pickFolder(dest, slug, manifest, ownedFolders) {
  const recorded = manifest?.get(slug)?.folder;
  if (recorded) return recorded;
  const base = safeFolder(slug);
  let candidate = base;
  let n = 1;
  for (;;) {
    const target = path.join(dest, candidate);
    if (!(await exists(target))) return candidate;
    if (ownedFolders.has(candidate) || (await folderBelongsTo(target, slug))) return candidate;
    n += 1;
    candidate = n === 2 ? `${base}-tm` : `${base}-tm-${n - 1}`;
  }
}
