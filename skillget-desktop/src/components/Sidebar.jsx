export default function Sidebar({ view, onView, categories, category, onCategory, query, onQuery, health }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">sg</span>
        <div>
          <h1>skillget</h1>
          <p>Skills for your agent</p>
        </div>
      </div>

      <label className="search">
        <span className="search-icon">⌕</span>
        <input
          type="search"
          value={query}
          placeholder="Search TypingMind…"
          onChange={(e) => onQuery(e.target.value)}
          aria-label="Search the TypingMind skill catalog"
        />
        {query && (
          <button className="search-clear" onClick={() => onQuery("")} aria-label="Clear search">
            ×
          </button>
        )}
      </label>

      <nav className="nav">
        <button className={view === "browse" ? "nav-item active" : "nav-item"} onClick={() => onView("browse")}>
          <span>Browse</span>
          <span className="nav-hint">catalog</span>
        </button>
        <button className={view === "installed" ? "nav-item active" : "nav-item"} onClick={() => onView("installed")}>
          <span>Installed</span>
          <span className="nav-hint">{health ? health.tracked : "—"}</span>
        </button>
      </nav>

      <div className="cats">
        <p className="cats-label">Categories</p>
        <div className="cats-scroll">
          {categories.length === 0 && <p className="muted small">Loading categories…</p>}
          {categories.map((c) => (
            <button
              key={c.slug}
              className={view === "browse" && c.slug === category ? "cat active" : "cat"}
              onClick={() => onCategory(c.slug)}
            >
              <span>{c.label}</span>
              <span className="cat-count">{c.count == null ? "…" : c.count.toLocaleString()}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="sidebar-foot">
        <p className="foot-label">Install destination</p>
        <code title={health?.dest}>~/.agents/skills</code>
        <p className="muted small">
          {health ? `${health.libraryFolders.toLocaleString()} folders` : "…"} · quiet by default
        </p>
      </div>
    </aside>
  );
}
