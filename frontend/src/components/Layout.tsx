import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

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
  return (
    <div className="shell">
      <header className="header">
        <div className="header-inner">
          <span className="brand">ResearchGraph</span>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>
              Dashboard
            </NavLink>
            <NavLink to="/papers">Papers</NavLink>
          </nav>
          <button type="button" className="btn" onClick={next} aria-label={`Theme: ${theme}. Click to change.`}>
            Theme: {theme}
          </button>
        </div>
      </header>
      <main className="main">
        <Outlet />
      </main>
      <footer className="footer">
        Metrics describe the ingested citation graph only; they are not measures of research quality.
      </footer>
    </div>
  );
}
