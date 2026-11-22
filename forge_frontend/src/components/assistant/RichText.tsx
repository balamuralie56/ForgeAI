import type { ReactNode } from "react";
import { CodeViewer } from "../CodeViewer";

const LANGUAGE_TO_EXT: Record<string, string> = {
  python: "py",
  py: "py",
  javascript: "js",
  js: "js",
  jsx: "jsx",
  typescript: "ts",
  ts: "ts",
  tsx: "tsx",
  json: "json",
  yaml: "yml",
  yml: "yml",
  bash: "sh",
  sh: "sh",
  shell: "sh",
  powershell: "sh",
  sql: "sql",
  html: "html",
  css: "css",
  markdown: "md",
  md: "md",
};

type Block = { kind: "text"; text: string } | { kind: "code"; language: string; text: string };

/** Splits model output into prose and fenced code blocks (an unclosed fence runs to the end). */
function parseBlocks(source: string): Block[] {
  const blocks: Block[] = [];
  const lines = source.split("\n");
  let text: string[] = [];
  let code: string[] | null = null;
  let language = "";
  const flushText = () => {
    const joined = text.join("\n").replace(/^\n+|\n+$/g, "");
    if (joined) blocks.push({ kind: "text", text: joined });
    text = [];
  };
  for (const line of lines) {
    const fence = line.match(/^\s*(```|~~~)\s*([\w+#.-]*)/);
    if (fence && code === null) {
      flushText();
      code = [];
      language = fence[2].toLowerCase();
    } else if (fence && code !== null) {
      blocks.push({ kind: "code", language, text: code.join("\n") });
      code = null;
    } else if (code !== null) {
      code.push(line);
    } else {
      text.push(line);
    }
  }
  if (code !== null) blocks.push({ kind: "code", language, text: code.join("\n") });
  flushText();
  return blocks;
}

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={i}>{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

/** Renders model output safely: prose with inline code/bold, and highlighted code blocks. */
export function RichText({ text }: { text: string }) {
  const blocks = parseBlocks(text);
  return (
    <div className="rich">
      {blocks.map((block, i) =>
        block.kind === "code" ? (
          <div className="rich__code" key={i}>
            {block.language && <span className="rich__lang">{block.language}</span>}
            <CodeViewer
              path={`snippet.${LANGUAGE_TO_EXT[block.language] ?? "txt"}`}
              content={block.text}
            />
          </div>
        ) : (
          <p className="rich__text" key={i}>
            {renderInline(block.text)}
          </p>
        ),
      )}
    </div>
  );
}
