import { useMemo, useState } from "react";
import type { FileEntry, FileTreeNode } from "../types";

function buildTree(files: FileEntry[]): FileTreeNode[] {
  const root: FileTreeNode[] = [];

  for (const file of files) {
    const parts = file.path.split("/");
    let level = root;
    let currentPath = "";

    parts.forEach((part, i) => {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isFile = i === parts.length - 1;

      let node = level.find((n) => n.name === part && n.isDir === !isFile);
      if (!node) {
        node = {
          name: part,
          path: currentPath,
          isDir: !isFile,
          children: isFile ? undefined : [],
        };
        level.push(node);
      }

      if (isFile) {
        node.sizeBytes = file.size_bytes;
      } else {
        level = node.children!;
      }
    });
  }

  const sortTree = (nodes: FileTreeNode[]) => {
    nodes.sort((a, b) => (a.isDir === b.isDir ? a.name.localeCompare(b.name) : a.isDir ? -1 : 1));
    nodes.forEach((n) => n.children && sortTree(n.children));
  };
  sortTree(root);
  return root;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function TreeNode({
  node,
  selected,
  onSelect,
  depth,
}: {
  node: FileTreeNode;
  selected: string | null;
  onSelect: (path: string) => void;
  depth: number;
}) {
  const [open, setOpen] = useState(true);
  const indent = { paddingLeft: `${depth * 14 + 10}px` };

  if (node.isDir) {
    return (
      <div>
        <button type="button" className="file-tree__dir" style={indent} onClick={() => setOpen((o) => !o)}>
          <span className="file-tree__chevron">{open ? "▾" : "▸"}</span>
          <span className="file-tree__name">{node.name}</span>
        </button>
        {open &&
          node.children?.map((child) => (
            <TreeNode key={child.path} node={child} selected={selected} onSelect={onSelect} depth={depth + 1} />
          ))}
      </div>
    );
  }

  return (
    <button
      type="button"
      className={`file-tree__file ${selected === node.path ? "file-tree__file--active" : ""}`}
      style={indent}
      onClick={() => onSelect(node.path)}
    >
      <span className="file-tree__name">{node.name}</span>
      {typeof node.sizeBytes === "number" && (
        <span className="file-tree__size">{formatSize(node.sizeBytes)}</span>
      )}
    </button>
  );
}

export function FileTree({
  files,
  selected,
  onSelect,
}: {
  files: FileEntry[];
  selected: string | null;
  onSelect: (path: string) => void;
}) {
  const tree = useMemo(() => buildTree(files), [files]);

  if (files.length === 0) {
    return <div className="file-tree__empty">No files yet.</div>;
  }

  return (
    <div className="file-tree">
      {tree.map((node) => (
        <TreeNode key={node.path} node={node} selected={selected} onSelect={onSelect} depth={0} />
      ))}
    </div>
  );
}
