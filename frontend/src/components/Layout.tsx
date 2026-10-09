import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { BookIcon, DocIcon, GridIcon, LayersIcon, NetworkIcon, SunMoonIcon, TagIcon, UsersIcon } from "./Icons";
import { SearchBox } from "./SearchBox";

type Theme = "system" | "light" | "dark";
const THEMES: Theme[] = ["system", "light", "dark"];
const STORAGE_KEY = "rg-theme";

function readTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return THEMES.includes(stored as Theme) ? (stored as Theme) : "system";
  } catch {
    return "system"; // storage can be blocked; the theme is only a convenience
  }
}

function useTheme() {
  const [theme, setTheme] = useState<Theme>(readTheme);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  const next = () => setTheme((t) => THEMES[(THEMES.indexOf(t) + 1) % THEMES.length] ?? "system");
  return { theme, next };
}

export function Layout() {
  const { theme, next } = useTheme();
  const bleed = useLocation().pathname.startsWith("/graph");
  return (
    <div className="app">
      <aside className="sidebar">
        <Link to="/" className="brand">
          <span className="brand-mark">
            <NetworkIcon size={18} />
          </span>
          ResearchGraph
        </Link>
        <SearchBox />
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end>
            <GridIcon /> Dashboard
          </NavLink>
          <NavLink to="/graph">
            <NetworkIcon /> Graph explorer
          </NavLink>
          <NavLink to="/ask">
            <BookIcon /> Ask the literature
          </NavLink>
          <NavLink to="/query">
            <GridIcon /> Query the graph
          </NavLink>
          <NavLink to="/papers">
            <DocIcon /> Papers
          </NavLink>
          <NavLink to="/authors">
            <UsersIcon /> Authors
          </NavLink>
          <NavLink to="/topics">
            <TagIcon /> Topics
          </NavLink>
          <NavLink to="/communities">
            <LayersIcon /> Communities
          </NavLink>
        </nav>
        <div className="sidebar-foot">
          <button type="button" className="btn btn-sm" onClick={next} aria-label={`Theme: ${theme}. Click to change.`}>
            <SunMoonIcon /> Theme: {theme}
          </button>
          <p className="sidebar-note">
            Metrics describe the ingested citation graph only; they are not measures of research quality.
          </p>
        </div>
      </aside>
      <main className={bleed ? "main main--bleed" : "main"}>
        <Outlet />
      </main>
    </div>
  );
}
