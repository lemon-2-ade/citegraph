import { useEffect, useState } from "react";

import { readTokens, type Tokens } from "./encode";

/** Theme-aware colour tokens; re-read when the theme toggle or the OS setting changes. */
export function useTokens(): Tokens {
  const [tokens, setTokens] = useState<Tokens>(readTokens);
  useEffect(() => {
    const update = () => setTokens(readTokens());
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    media?.addEventListener("change", update);
    return () => {
      observer.disconnect();
      media?.removeEventListener("change", update);
    };
  }, []);
  return tokens;
}
