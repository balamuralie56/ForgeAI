import { useMemo } from "react";
import Prism from "prismjs";
import "prismjs/components/prism-python";
import "prismjs/components/prism-javascript";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-jsx";
import "prismjs/components/prism-tsx";
import "prismjs/components/prism-json";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-markdown";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-sql";
import "prismjs/components/prism-docker";

const EXT_TO_LANG: Record<string, string> = {
  py: "python",
  js: "jsx",
  mjs: "jsx",
  jsx: "jsx",
  ts: "tsx",
  tsx: "tsx",
  json: "json",
  yml: "yaml",
  yaml: "yaml",
  md: "markdown",
  sh: "bash",
  bash: "bash",
  sql: "sql",
  html: "markup",
  htm: "markup",
  xml: "markup",
  css: "css",
  env: "bash",
};

function languageFor(path: string): string {
  const name = path.split("/").pop() ?? path;
  if (name.toLowerCase() === "dockerfile") return "docker";
  const ext = name.includes(".") ? (name.split(".").pop() ?? "").toLowerCase() : "";
  return EXT_TO_LANG[ext] ?? "clike";
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c] ?? c);
}

export function CodeViewer({ path, content }: { path: string; content: string }) {
  const { html, lineCount } = useMemo(() => {
    const lang = languageFor(path);
    const grammar = Prism.languages[lang];
    let highlighted: string;
    try {
      highlighted = grammar ? Prism.highlight(content, grammar, lang) : escapeHtml(content);
    } catch {
      highlighted = escapeHtml(content);
    }
    return { html: highlighted, lineCount: content.length ? content.split("\n").length : 1 };
  }, [path, content]);

  return (
    <div className="code-viewer">
      <div className="code-viewer__gutter" aria-hidden="true">
        {Array.from({ length: lineCount }, (_, i) => (
          <span key={i}>{i + 1}</span>
        ))}
      </div>
      <pre className="code-viewer__code">
        <code dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    </div>
  );
}
