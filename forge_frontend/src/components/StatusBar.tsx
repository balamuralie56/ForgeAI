import { useEffect, useState } from "react";
import { api } from "../api";
import type { Diagnostics } from "../types";
import type { ConnectionState } from "../useEventStream";

export function StatusBar({ connectionState }: { connectionState: ConnectionState }) {
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api
        .getDiagnostics()
        .then((d) => !cancelled && setDiagnostics(d))
        .catch((e) => !cancelled && setError(e.message));
    };
    load();
    const interval = window.setInterval(load, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const ollamaOnline = diagnostics?.ollama_status.startsWith("Online");

  return (
    <header className="status-bar">
      <div className="status-bar__brand">
        <span className="status-bar__logo">FORGE</span>
        <span className="status-bar__version">
          {diagnostics ? `v${diagnostics.version}` : "…"}
        </span>
      </div>
      <div className="status-bar__items">
        <StatusPill
          label="API"
          state={
            error ? "down" : connectionState === "open" ? "up" : "warn"
          }
          detail={error ?? connectionState}
        />
        <StatusPill
          label="Ollama"
          state={diagnostics ? (ollamaOnline ? "up" : "down") : "warn"}
          detail={diagnostics?.ollama_status ?? "checking…"}
        />
        <StatusPill
          label="Model"
          state="neutral"
          detail={diagnostics?.default_model ?? "…"}
        />
        <StatusPill
          label="Plugins"
          state="neutral"
          detail={diagnostics ? `${diagnostics.enabled_plugins.length} loaded` : "…"}
        />
      </div>
    </header>
  );
}

function StatusPill({
  label,
  state,
  detail,
}: {
  label: string;
  state: "up" | "down" | "warn" | "neutral";
  detail: string;
}) {
  return (
    <div className={`pill pill--${state}`} title={detail}>
      <span className="pill__dot" />
      <span className="pill__label">{label}</span>
      <span className="pill__detail">{detail}</span>
    </div>
  );
}
