import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api";
import { FileTree } from "../FileTree";
import { CodeViewer } from "../CodeViewer";
import { ValidationPanel } from "../ValidationPanel";
import type { FileEntry } from "../../types";

type PreviewState =
  | { status: "loading" }
  | { status: "ready"; content: string }
  | { status: "error"; message: string };

/** File tree + code preview for a workflow's workspace. Polls while the
 * workflow is active so files appear as each stage writes them, not only
 * once the whole run finishes. `reportReady` turns on the validation panel
 * once the Developer stage has produced its implementation report. */
export function FilesTab({
  workflowId,
  isActive,
  reportReady,
}: {
  workflowId: string;
  isActive: boolean;
  reportReady: boolean;
}) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewState>({ status: "loading" });
  const intervalRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      api
        .listFiles(workflowId)
        .then((res) => !cancelled && setFiles(res.files))
        .catch(() => {
          /* transient - next poll (or the terminal refresh) will retry */
        });
    };
    refresh();
    if (isActive) {
      intervalRef.current = window.setInterval(refresh, 3000);
    }
    return () => {
      cancelled = true;
      window.clearInterval(intervalRef.current);
    };
  }, [workflowId, isActive]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    api
      .getFile(workflowId, selected)
      .then((res) => !cancelled && setPreview({ status: "ready", content: res.content }))
      .catch(
        (e) =>
          !cancelled &&
          setPreview({
            status: "error",
            message: e instanceof ApiError ? e.message : String(e),
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [workflowId, selected]);

  return (
    <div className="tab-panel tab-panel--files">
      <ValidationPanel
        enabled={reportReady}
        onOpenFile={(path) => {
          setPreview({ status: "loading" });
          setSelected(path);
        }}
      />
      <div className="files-tab">
        <div className="files-tab__tree">
          <FileTree
            files={files}
            selected={selected}
            onSelect={(path) => {
              setPreview({ status: "loading" });
              setSelected(path);
            }}
          />
        </div>
        <div className="files-tab__preview">
          {!selected && <div className="report-gate__empty">Select a file to preview it.</div>}
          {selected && preview.status === "loading" && (
            <div className="report-gate__empty">Loading…</div>
          )}
          {selected && preview.status === "error" && (
            <div className="report-gate__error">{preview.message}</div>
          )}
          {selected && preview.status === "ready" && (
            <CodeViewer path={selected} content={preview.content} />
          )}
        </div>
      </div>
    </div>
  );
}
