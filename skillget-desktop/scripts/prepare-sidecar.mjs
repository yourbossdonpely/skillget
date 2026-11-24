// Stage the Node engine next to the Tauri binary: node.exe + server/ + frontend/.
// These files are build inputs, not source, so they are gitignored.
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const OUT = path.join(ROOT, "src-tauri", "resources");

const node = process.env.SKILLGET_NODE || process.execPath;

try {
  await fs.access(path.join(ROOT, "dist", "index.html"));
} catch {
  console.error("dist/index.html missing - run `npm run build` first");
  process.exit(1);
}

await fs.rm(OUT, { recursive: true, force: true });
await fs.mkdir(OUT, { recursive: true });
await fs.copyFile(node, path.join(OUT, "node.exe"));
await fs.cp(path.join(ROOT, "server"), path.join(OUT, "server"), { recursive: true });
await fs.cp(path.join(ROOT, "dist"), path.join(OUT, "frontend"), { recursive: true });

// The engine's only runtime dependency. Without this the installed app fails with
// ERR_MODULE_NOT_FOUND (the in-repo run finds node_modules by walking up).
const serverModules = path.join(OUT, "server", "node_modules");
for (const pkg of ["js-yaml", "argparse"]) {
  await fs.cp(path.join(ROOT, "node_modules", pkg), path.join(serverModules, pkg), {
    recursive: true,
  });
}

const size = (await fs.stat(path.join(OUT, "node.exe"))).size;
console.log(`staged ${OUT}`);
console.log(`  node.exe ${(size / 1024 / 1024).toFixed(1)} MB from ${node}`);
