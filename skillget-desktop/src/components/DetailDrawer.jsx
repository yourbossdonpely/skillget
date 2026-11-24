import { compact, timeAgo } from "../api.js";

export default function DetailDrawer({
  slug,
  detail,
  loading,
  installing,
  quiet,
  onQuietChange,
  onInstall,
  onClose,
}) {
  const skill = detail?.skill;

  return (
    <div className="drawer-wrap" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <header className="drawer-head">
          <div>
            <p className="eyebrow">{loading ? "Loading" : "Skill"}</p>
            <h2>{skill?.name ?? slug}</h2>
            <p className="slug">{slug}</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close detail">
            ×
          </button>
        </header>

        <div className="drawer-body">
          {loading && <div className="skeleton block" />}

          {skill && (
            <>
              <p className="desc">{skill.description}</p>

              <div className="chips">
                {skill.license && <span className="chip">{skill.license}</span>}
                <span className="chip">★ {compact(skill.stars)}</span>
                <span className="chip">{skill.resources.length} resource{skill.resources.length === 1 ? "" : "s"}</span>
                {skill.categories.map((c) => (
                  <span key={c} className="chip muted">
                    {c}
                  </span>
                ))}
              </div>

              {skill.sourceURL && (
                <a className="source" href={skill.sourceURL} target="_blank" rel="noreferrer">
                  {skill.sourceURL.replace(/^https?:\/\//, "")}
                </a>
              )}

              <section className="install-box">
                {detail.installed ? (
                  <>
                    <p className="installed-line">
                      <span className="dot ok" /> Installed as <code>{detail.installedFolder}</code>
                    </p>
                    <p className="muted small">
                      {detail.installedQuiet ? "Quiet" : "Auto-injected"} · {timeAgo(detail.installedAt)} ·{" "}
                      {compact(detail.skillMdBytes)} B SKILL.md
                    </p>
                    <button className="btn btn-ghost wide" onClick={onInstall} disabled={installing}>
                      {installing ? "Reinstalling…" : "Reinstall / refresh"}
                    </button>
                  </>
                ) : (
                  <>
                    <label className="check">
                      <input type="checkbox" checked={quiet} onChange={(e) => onQuietChange(e.target.checked)} />
                      <span>
                        Install quietly
                        <em>Adds metadata.opencode/autoinvoke: false — stays loadable by ID, out of the prompt.</em>
                      </span>
                    </label>
                    <button className="btn wide" onClick={onInstall} disabled={installing}>
                      {installing ? "Installing…" : "Install to ~/.agents/skills"}
                    </button>
                  </>
                )}
              </section>

              {skill.resources.length > 0 && (
                <section>
                  <h4>Resources</h4>
                  <ul className="files">
                    {skill.resources.map((r) => (
                      <li key={r.path}>
                        <code>{r.path}</code>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <section>
                <h4>SKILL.md</h4>
                <pre className="md-preview">{skill.bodyMarkdown || "(no body markdown in the catalog payload)"}</pre>
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
