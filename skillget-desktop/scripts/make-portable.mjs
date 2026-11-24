// Assemble a self-contained portable folder and zip it.
// Layout: skillget.exe + resources/{node.exe, server/, frontend/}
import fs from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const RELEASE = path.join(ROOT, "src-tauri", "target", "release");
const RESOURCES = path.join(ROOT, "src-tauri", "resources");
const OUT = path.join(ROOT, "src-tauri", "target", "portable");
const STAGE = path.join(OUT, "skillget");
const version = JSON.parse(await fs.readFile(path.join(ROOT, "package.json"), "utf8")).version;
const zip = path.join(OUT, `skillget-${version}-windows-portable.zip`);

await fs.rm(OUT, { recursive: true, force: true });
await fs.mkdir(STAGE, { recursive: true });
await fs.copyFile(path.join(RELEASE, "skillget.exe"), path.join(STAGE, "skillget.exe"));
await fs.cp(RESOURCES, path.join(STAGE, "resources"), { recursive: true });

const result = spawnSync(
  "powershell",
  [
    "-NoProfile",
    "-Command",
    `Compress-Archive -Path '${STAGE}' -DestinationPath '${zip}' -CompressionLevel Optimal -Force`,
  ],
  { stdio: "inherit" },
);
if (result.status !== 0) process.exit(result.status ?? 1);

const stat = await fs.stat(zip);
console.log(`portable zip: ${zip} (${(stat.size / 1024 / 1024).toFixed(1)} MB)`);
