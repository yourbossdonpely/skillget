import { useEffect, useState } from "react";
import { api, compact, timeAgo } from "../api.js";

export default function InstalledView({ onOpen }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.installed().then(setData).catch((err) => setError(err.message));
  }, []);

  if (error) return <div className="banner error">{error}</div>;
  if (!data) return <div className="skeleton block" />;

  return (
    <div className="installed">
      <div className="stats">
        <div className="stat">
          <p className="stat-label">Destination</p>
          <code className="stat-value small-value" title={data.dest}>
            {data.dest}
          </code>
        </div>
        <div className="stat">
          <p className="stat-label">Installed by this app</p>
          <p className="stat-value">{data.tracked}</p>
        </div>
        <div className="stat">
          <p className="stat-label">Healthy on disk</p>
          <p className="stat-value">{data.healthy}</p>
        </div>
        <div className="stat">
          <p className="stat-label">Quiet</p>
          <p className="stat-value">
            {data.quiet}
            <span className="muted"> / {data.tracked}</span>
          </p>
        </div>
        <div className="stat">
          <p className="stat-label">Folders in library</p>
          <p className="stat-value">{data.libraryFolders.toLocaleString()}</p>
        </div>
      </div>

      {data.rows.length === 0 ? (
        <div className="empty">
          <p>Nothing installed from this app yet.</p>
          <p className="muted small">
            Browse a category, open a skill and press install — it lands in <code>{data.dest}</code>.
          </p>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Skill</th>
              <th>Folder</th>
              <th>Installed</th>
              <th>SKILL.md</th>
              <th>Mode</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.slug}>
                <td>
                  <button className="link" onClick={() => onOpen(row.slug)}>
                    {row.name}
                  </button>
                  <p className="slug">{row.slug}</p>
                </td>
                <td>
                  <code>{row.folder}</code>
                  {row.files > 0 && <p className="muted small">{row.files} files</p>}
                </td>
                <td title={row.installedAt}>{timeAgo(row.installedAt)}</td>
                <td>{row.skillMd === "raw" ? "upstream" : "synthesized"}</td>
                <td>{row.quiet ? <span className="chip ok-chip">quiet</span> : <span className="chip">injected</span>}</td>
                <td>
                  {row.onDisk ? (
                    <>
                      <span className="dot ok" /> {compact(row.skillMdBytes)} B
                    </>
                  ) : (
                    <>
                      <span className="dot bad" /> missing
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
