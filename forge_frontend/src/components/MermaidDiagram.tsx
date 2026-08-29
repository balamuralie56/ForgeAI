import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

let initialized = false;
function ensureInit() {
  if (initialized) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: "dark",
    themeVariables: {
      background: "#12161b",
      primaryColor: "#191f26",
      primaryTextColor: "#e6ebf0",
      primaryBorderColor: "#ff7a3d",
      lineColor: "#7c8894",
      secondaryColor: "#3a2417",
      tertiaryColor: "#0b0e11",
      fontFamily: "IBM Plex Mono, ui-monospace, monospace",
      fontSize: "13px",
    },
  });
  initialized = true;
}

let counter = 0;

type RenderState =
  | { status: "rendering" }
  | { status: "ready"; svg: string }
  | { status: "error"; message: string };

/** Renders one named Mermaid diagram. A malformed definition (real LLM output
 * isn't guaranteed valid) shows an inline error, never crashes the tab. */
export function MermaidDiagram({
  title,
  definition,
}: {
  title: string;
  definition: string;
}) {
  const [state, setState] = useState<RenderState>({ status: "rendering" });
  const idRef = useRef(`mermaid-${counter++}`);

  useEffect(() => {
    ensureInit();
    let cancelled = false;
    mermaid
      .render(idRef.current, definition)
      .then((result) => !cancelled && setState({ status: "ready", svg: result.svg }))
      .catch(
        (e) =>
          !cancelled &&
          setState({ status: "error", message: e instanceof Error ? e.message : String(e) }),
      );
    return () => {
      cancelled = true;
    };
  }, [definition]);

  return (
    <div className="mermaid-diagram">
      <div className="mermaid-diagram__title">{title}</div>
      {state.status === "error" && (
        <div className="mermaid-diagram__error">Couldn't render this diagram: {state.message}</div>
      )}
      {state.status === "ready" && (
        <div className="mermaid-diagram__svg" dangerouslySetInnerHTML={{ __html: state.svg }} />
      )}
      {state.status === "rendering" && (
        <div className="mermaid-diagram__loading">Rendering…</div>
      )}
    </div>
  );
}
