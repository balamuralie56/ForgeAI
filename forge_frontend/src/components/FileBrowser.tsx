import { useEffect, useState } from "react";
import { api } from "../api";
import type { FileEntry } from "../types";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileBrowser({ workflowId }: { workflowId: string }) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listFiles(workflowId)
      .then((res) => !cancelled && setFiles(res.files))
      .catch((e) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    api
      .getFile(workflowId, selected)
      .then((res) => !cancelled && setContent(res.content))
      .catch((e) => !cancelled && setContent(`Failed to load: ${e.message}`));
    return () => {
      cancelled = true;
    };
  }, [workflowId, selected]);

  if (loadError) return <div className="file-browser__empty">{loadError}</div>;
  if (files.length === 0) return <div className="file-browser__empty">No files generated yet.</div>;

  return (
    <div className="file-browser">
      <div className="file-browser__list">
        {files.map((f) => (
          <button
            key={f.path}
            className={`file-browser__item ${selected === f.path ? "file-browser__item--active" : ""}`}
            onClick={() => setSelected(f.path)}
          >
            <span className="file-browser__path">{f.path}</span>
            <span className="file-browser__size">{formatSize(f.size_bytes)}</span>
          </button>
        ))}
      </div>
      <pre className="file-browser__content">
        {selected ? content : "Select a file to preview it."}
      </pre>
    </div>
  );
}
