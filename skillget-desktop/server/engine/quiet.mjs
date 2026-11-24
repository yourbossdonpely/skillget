// Minimal port of tools/quiet.py: add metadata.opencode/autoinvoke: false so an
// installed skill stays out of the auto-injected prompt but remains loadable by ID.
// Line-based edits keep the original YAML quoting, ordering and comments intact.
import yaml from "js-yaml";

const FLAG = "opencode/autoinvoke";
const FLAG_RE = new RegExp(`^\\s*["']?${FLAG.replace("/", "\\/")}["']?\\s*:\\s*(.*)$`);
const META_RE = /^["']?metadata["']?\s*:\s*(.*)$/;
const DISABLE_RE = /^\s*["']?disable-model-invocation["']?\s*:\s*(.*)$/;
const FLAG_ANY_RE = new RegExp(
  `${FLAG.replace("/", "\\/")}\\s*:\\s*["']?(true|false|yes|no|on|off|1|0)`,
  "gi",
);

function splitFrontmatter(text) {
  let src = text;
  if (src.charCodeAt(0) === 0xfeff) src = src.slice(1);
  const nl = src.slice(0, 200).includes("\r\n") ? "\r\n" : "\n";
  const lines = src.split(nl);
  if (!lines.length || lines[0].trim() !== "---") return null;
  for (let i = 1; i < lines.length; i += 1) {
    if (lines[i].trim() === "---") {
      return { fm: lines.slice(1, i), body: lines.slice(i + 1).join(nl), nl };
    }
  }
  return null;
}

const truthy = (v) => ["true", "yes", "on", "1"].includes(String(v).trim().replace(/^["']|["']$/g, "").toLowerCase());

function falseIn(line) {
  FLAG_ANY_RE.lastIndex = 0;
  const m = FLAG_ANY_RE.exec(line);
  return Boolean(m) && !truthy(m[1]);
}

export function alreadyQuiet(fm) {
  for (const line of fm) {
    const disable = DISABLE_RE.exec(line);
    if (disable && truthy(disable[1])) return true;
    FLAG_ANY_RE.lastIndex = 0;
    const flag = FLAG_ANY_RE.exec(line);
    if (flag && !truthy(flag[1])) return true;
  }
  return false;
}

function blockChildIndent(fm, idx) {
  const parent = fm[idx].length - fm[idx].replace(/^\s+/, "").length;
  for (const line of fm.slice(idx + 1)) {
    if (!line.trim()) continue;
    const indent = line.length - line.replace(/^\s+/, "").length;
    return " ".repeat(indent > parent ? indent : parent + 2);
  }
  return " ".repeat(parent + 2);
}

function mark(fm) {
  if (alreadyQuiet(fm)) return { fm, status: "already" };

  for (let idx = 0; idx < fm.length; idx += 1) {
    const line = fm[idx];
    const m = FLAG_RE.exec(line);
    if (m) {
      const indent = line.slice(0, line.length - line.trimStart().length);
      const key = line.split(":", 1)[0].trim();
      const trailing = line.trimEnd().endsWith(",") ? "," : "";
      const next = `${indent}${key}: false${trailing}`;
      if (next === line) return { fm, status: "already" };
      fm[idx] = next;
      return { fm, status: "updated" };
    }
  }

  for (let idx = 0; idx < fm.length; idx += 1) {
    const line = fm[idx];
    const m = META_RE.exec(line);
    if (!m) continue;
    FLAG_ANY_RE.lastIndex = 0;
    if (FLAG_ANY_RE.test(line)) {
      // Inline map that already names the flag: flip it instead of adding a key.
      FLAG_ANY_RE.lastIndex = 0;
      const next = line.replace(FLAG_ANY_RE, `${FLAG}: false`);
      if (next === line) return { fm, status: "already" };
      fm[idx] = next;
      return { fm, status: "updated" };
    }
    const value = m[1].trim();
    if (["", "null", "~"].includes(value)) {
      const child = fm.findIndex((l, k) => k > idx && l.trim());
      if (child !== -1 && fm[child].trimStart().startsWith("{")) {
        // A block key cannot precede a flow mapping, so the flag goes in the braces.
        const flow = fm[child];
        const stripped = flow.trimStart();
        const lead = flow.slice(0, flow.length - stripped.length);
        const inner = stripped.slice(1).trimStart();
        fm[child] = inner === "}" ? `${lead}{${FLAG}: false}}` : `${lead}{${FLAG}: false, ${inner}`;
        return { fm, status: "added" };
      }
      fm[idx] = "metadata:";
      fm.splice(idx + 1, 0, `${blockChildIndent(fm, idx)}${FLAG}: false`);
      return { fm, status: "added" };
    }
    if (value.startsWith("{") && value.endsWith("}")) {
      const inner = value.slice(1, -1).trim();
      fm[idx] = inner ? `metadata: { ${FLAG}: false, ${inner} }` : `metadata: { ${FLAG}: false }`;
      return { fm, status: "added" };
    }
    if (value.startsWith("{")) {
      const brace = line.indexOf("{");
      const rest = line.slice(brace + 1).trim();
      fm[idx] = `${line.slice(0, brace + 1)} ${FLAG}: false,${rest ? ` ${rest}` : ""}`;
      return { fm, status: "added" };
    }
    return { fm, status: "unparsed" };
  }

  fm.push("metadata:");
  fm.push(`  ${FLAG}: false`);
  return { fm, status: "added" };
}

/** Only write frontmatter we can still parse as a YAML mapping. */
export function yamlOk(fmLines) {
  try {
    return yaml.load(fmLines.join("\n")) instanceof Object;
  } catch {
    return false;
  }
}

/**
 * Return {text, status}. `prepended` means it had no frontmatter at all and a
 * minimal one was added; `unverified` means the edit failed the YAML check and
 * the original text is returned untouched.
 */
export function ensureQuiet(text, name = "skill", description = "") {
  const parsed = splitFrontmatter(text);
  if (!parsed) {
    const lines = ["---", `name: ${JSON.stringify(name || "skill")}`];
    if (description) lines.push(`description: ${JSON.stringify(description)}`);
    lines.push("metadata:", `  ${FLAG}: false`, "---", "");
    return { text: `${lines.join("\n")}${text}`, status: "prepended" };
  }
  const { fm, body, nl } = parsed;
  const result = mark(fm);
  if (["already", "unparsed"].includes(result.status)) {
    return { text, status: result.status };
  }
  if (!yamlOk(result.fm)) return { text, status: "unverified" };
  return { text: `${["---", ...result.fm, "---"].join(nl)}${nl}${body}`, status: result.status };
}
