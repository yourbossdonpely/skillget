import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import Sidebar from "./components/Sidebar.jsx";
import SkillGrid from "./components/SkillGrid.jsx";
import DetailDrawer from "./components/DetailDrawer.jsx";
import InstalledView from "./components/InstalledView.jsx";

export const PAGE_SIZE = 51;

function Toasts({ toasts }) {
  return (
    <div className="toasts">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          {t.message}
        </div>
      ))}
    </div>
  );
}

function PageControls({ page, total, onChange }) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (pages <= 1) return null;
  return (
    <div className="pager">
      <button className="icon-btn" onClick={() => onChange(page - 1)} disabled={page <= 1} aria-label="Previous page">
        ←
      </button>
      <span>
        {page} <span className="muted">/ {pages}</span>
      </span>
      <button className="icon-btn" onClick={() => onChange(page + 1)} disabled={page >= pages} aria-label="Next page">
        →
      </button>
    </div>
  );
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [categories, setCategories] = useState([]);
  const [view, setView] = useState("browse");
  const [category, setCategory] = useState("software-development");
  const [sort, setSort] = useState("stars");
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [detailSlug, setDetailSlug] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [installing, setInstalling] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [installedVersion, setInstalledVersion] = useState(0);
  const [quiet, setQuiet] = useState(true);

  const toast = useCallback((message, kind = "ok") => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((list) => [...list, { id, message, kind }]);
    setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 6000);
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch((err) => setError(err.message));
    api
      .categories()
      .then((data) => setCategories(data.categories))
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), 350);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (debounced.length >= 2) {
      setView("search");
      setPage(1);
    } else if (view === "search") {
      setView("browse");
      setPage(1);
    }
    // view is only read to avoid clobbering the Installed tab
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  useEffect(() => {
    if (view === "installed") return;
    if (view === "search" && debounced.length < 2) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    const run =
      view === "search"
        ? api.search({ q: debounced, page, sort })
        : api.browse({ category, page, sort });
    run
      .then((data) => {
        if (!cancelled) setListing(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
          setListing(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [view, category, page, sort, debounced]);

  const openSkill = useCallback(
    async (slug) => {
      setDetailSlug(slug);
      setDetail(null);
      setDetailLoading(true);
      try {
        setDetail(await api.skill(slug));
      } catch (err) {
        toast(`Could not load ${slug}: ${err.message}`, "err");
        setDetailSlug(null);
      } finally {
        setDetailLoading(false);
      }
    },
    [toast],
  );

  const install = useCallback(
    async (slug) => {
      setInstalling(slug);
      try {
        const res = await api.install({ slug, quiet });
        setInstalledVersion((n) => n + 1);
        setHealth((h) => (h ? { ...h, libraryFolders: h.libraryFolders + 1 } : h));
        const failed = res.resourceFailures?.length ? ` · ${res.resourceFailures.length} file(s) failed` : "";
        toast(`Installed ${res.name || slug} → ${res.folder}${failed}`, "ok");
        setDetail((d) =>
          d && d.skill?.slug === slug
            ? { ...d, installed: true, installedFolder: res.folder, installedQuiet: res.quiet }
            : d,
        );
      } catch (err) {
        toast(`Install failed: ${err.message}`, "err");
      } finally {
        setInstalling(null);
      }
    },
    [quiet, toast],
  );

  const pickCategory = (slug) => {
    setCategory(slug);
    setPage(1);
    setView("browse");
  };

  const pickView = (next) => {
    setView(next);
    if (next === "browse") setQuery("");
  };

  const activeCategory = categories.find((c) => c.slug === category);
  const categoryLabel =
    activeCategory?.label ??
    category
      .split("-")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  const total = listing?.totalCount ?? 0;
  const title =
    view === "installed"
      ? "Installed"
      : view === "search"
        ? `Results for “${debounced}”`
        : categoryLabel;
  const eyebrow =
    view === "installed" ? "Your library" : view === "search" ? "TypingMind search" : "TypingMind catalog";

  return (
    <div className="app">
      <Sidebar
        view={view}
        onView={pickView}
        categories={categories}
        category={category}
        onCategory={pickCategory}
        query={query}
        onQuery={setQuery}
        health={health}
      />

      <main className="main">
        <header className="topbar">
          <div className="topbar-title">
            <p className="eyebrow">{eyebrow}</p>
            <h1>{title}</h1>
            {view !== "installed" && listing && (
              <p className="topbar-sub">
                {total.toLocaleString()} skills
                {view === "browse" ? ` in ${categoryLabel}` : ""} · installed into{" "}
                <code>~/.agents/skills</code>
              </p>
            )}
          </div>
          <div className="topbar-actions">
            {view !== "installed" && (
              <select
                className="select"
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value);
                  setPage(1);
                }}
                aria-label="Sort skills"
              >
                <option value="stars">Most stars</option>
                <option value="newest">Newest</option>
              </select>
            )}
            {view !== "installed" && (
              <PageControls
                page={page}
                total={total}
                onChange={(next) => {
                  setPage(next);
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
              />
            )}
          </div>
        </header>

        {error && <div className="banner error">{error}</div>}

        {view === "installed" ? (
          <InstalledView key={installedVersion} onOpen={openSkill} />
        ) : (
          <SkillGrid
            listing={listing}
            loading={loading}
            onOpen={openSkill}
            onInstall={install}
            installing={installing}
            emptyHint={
              view === "search"
                ? "No skills matched that search on TypingMind."
                : "This category returned nothing. Try another one."
            }
          />
        )}
      </main>

      {detailSlug && (
        <DetailDrawer
          slug={detailSlug}
          detail={detail}
          loading={detailLoading}
          installing={installing === detailSlug}
          quiet={quiet}
          onQuietChange={setQuiet}
          onInstall={() => install(detailSlug)}
          onClose={() => {
            setDetailSlug(null);
            setDetail(null);
          }}
        />
      )}

      <Toasts toasts={toasts} />
    </div>
  );
}
