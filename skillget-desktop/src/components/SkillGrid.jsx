import { compact } from "../api.js";

function Card({ skill, onOpen, onInstall, installing }) {
  return (
    <article className="card" onClick={() => onOpen(skill.slug)}>
      <div className="card-head">
        <h3>{skill.name}</h3>
        <button
          className="install-mini"
          disabled={installing}
          onClick={(e) => {
            e.stopPropagation();
            onInstall(skill.slug);
          }}
        >
          {installing ? "Installing…" : "Install"}
        </button>
      </div>
      <p className="slug">{skill.slug}</p>
      <p className="desc">{skill.description || "No description provided."}</p>
      <div className="card-meta">
        <span title={`${skill.stars} stars`}>★ {compact(skill.stars)}</span>
        <span>{skill.resourcesCount} file{skill.resourcesCount === 1 ? "" : "s"}</span>
        {skill.isPopular && <span className="pill">popular</span>}
      </div>
    </article>
  );
}

export default function SkillGrid({ listing, loading, onOpen, onInstall, installing, emptyHint }) {
  if (!listing && loading) {
    return (
      <div className="grid">
        {Array.from({ length: 9 }, (_, i) => (
          <div key={i} className="card skeleton" />
        ))}
      </div>
    );
  }
  if (!listing) return <div className="empty">Nothing loaded yet.</div>;
  if (!listing.skills?.length) return <div className="empty">{emptyHint}</div>;

  return (
    <>
      <div className={loading ? "grid dim" : "grid"}>
        {listing.skills.map((skill) => (
          <Card
            key={skill.slug}
            skill={skill}
            onOpen={onOpen}
            onInstall={onInstall}
            installing={installing === skill.slug}
          />
        ))}
      </div>
      {loading && <p className="muted small loading-line">Loading page…</p>}
    </>
  );
}
