import { useCallback, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "afm-theme";

/** Emitted whenever the theme changes so non-React consumers (e.g. the
 *  Cytoscape graph) can re-read CSS custom properties. */
export const THEME_EVENT = "afm:theme";

function currentTheme(): Theme {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "light" || attr === "dark") return attr;
  return "dark"; // Intelligence Terminal default
}

/** Resolved light/dark theme with a persisted manual override.
 *  Dark is the system-wide default; light applies only on explicit toggle. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(() =>
    typeof document === "undefined" ? "dark" : currentTheme()
  );

  const apply = useCallback((next: Theme) => {
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* storage may be unavailable */
    }
    setTheme(next);
    window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: next }));
  }, []);

  const toggle = useCallback(() => {
    apply(theme === "dark" ? "light" : "dark");
  }, [theme, apply]);

  return { theme, toggle };
}
