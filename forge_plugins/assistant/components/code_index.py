"""
Lexical code search over a project: files are split into chunks (one per
top-level Python definition, or fixed line windows for other languages) and
ranked with BM25 over identifier-aware tokens. Pure Python, no embedding
model, so it costs no extra RAM or disk and updates incrementally as files
change.
"""

import ast
import logging
import math
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .workspace import FileInfo, ProjectWorkspace

logger = logging.getLogger("ForgeAI.Plugins.Assistant.CodeIndex")

_WINDOW_LINES = 60
_WINDOW_STEP = 45
_MAX_CHUNK_LINES = 120

_BM25_K1 = 1.4
_BM25_B = 0.75

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "into", "are",
        "was", "were", "you", "your", "not", "but", "can", "has", "have",
        "how", "what", "why", "when", "where", "which", "who", "does", "did",
        "make", "made", "use", "using", "used", "add", "get", "set", "all",
        "any", "some", "one", "two", "its", "there", "then", "than", "them",
        "they", "will", "would", "should", "could", "please", "want", "need",
        "code", "file", "files", "function", "method", "class", "self", "def",
        "return", "import", "none", "true", "false", "let", "var", "const",
        "new", "null", "void", "public", "private", "static", "str", "int",
        "of", "to", "in", "on", "is", "it", "be", "or", "an", "as", "at", "by",
        "if", "do", "so", "we", "me", "my", "up", "no",
    }
)  # fmt: skip

# Regexes that find top-level definitions in non-Python sources, for the
# project map. Deliberately simple: they only need to be good enough to tell
# a small model which file defines what.
_SYMBOL_PATTERNS: Dict[str, Sequence[re.Pattern[str]]] = {
    "js": (
        re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)", re.M),
        re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)", re.M),
        re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", re.M),
        re.compile(r"^\s*(?:export\s+)?(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)", re.M),
    ),
    "go": (
        re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)", re.M),
        re.compile(r"^type\s+([A-Za-z_]\w*)", re.M),
    ),
    "rust": (
        re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)", re.M),
        re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|impl)\s+([A-Za-z_]\w*)", re.M),
    ),
    "c_like": (
        re.compile(r"^\s*(?:public|private|protected|internal)?\s*(?:static\s+)?(?:final\s+)?(?:abstract\s+)?(?:class|interface|enum|struct|record)\s+([A-Za-z_]\w*)", re.M),
    ),
}  # fmt: skip

_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "js", ".jsx": "js", ".ts": "js", ".tsx": "js", ".mjs": "js", ".cjs": "js",
    ".go": "go",
    ".rs": "rust",
    ".java": "c_like", ".cs": "c_like", ".kt": "c_like", ".swift": "c_like",
    ".cpp": "c_like", ".cc": "c_like", ".hpp": "c_like", ".h": "c_like", ".c": "c_like",
}  # fmt: skip

_FENCE_LANGUAGE = {
    ".py": "python", ".js": "javascript", ".jsx": "jsx", ".ts": "typescript",
    ".tsx": "tsx", ".json": "json", ".toml": "toml", ".yaml": "yaml",
    ".yml": "yaml", ".md": "markdown", ".html": "html", ".css": "css",
    ".go": "go", ".rs": "rust", ".java": "java", ".cs": "csharp",
    ".sh": "bash", ".ps1": "powershell", ".sql": "sql", ".c": "c",
    ".cpp": "cpp", ".h": "c",
}  # fmt: skip


def fence_language(path: str) -> str:
    """Returns the Markdown code-fence language for a file path."""
    return _FENCE_LANGUAGE.get(PurePosixPath(path).suffix.lower(), "")


def tokenize(text: str) -> List[str]:
    """
    Splits text into lowercase search tokens. Identifiers are kept whole and
    also split into their snake_case / camelCase parts, so `loadTasks`,
    `load_tasks` and "load the tasks" all match each other.

    Args:
        text (str): Code or natural language.

    Returns:
        List[str]: Tokens, stopwords and one-character tokens removed.
    """
    tokens: List[str] = []
    for word in _WORD.findall(text):
        lower = word.lower()
        parts: List[str] = []
        for piece in word.split("_"):
            parts.extend(p.lower() for p in _CAMEL.findall(piece))
        if len(parts) > 1 and len(lower) > 2 and lower not in _STOPWORDS:
            tokens.append(lower)
        for part in parts:
            if len(part) > 1 and part not in _STOPWORDS:
                tokens.append(part)
    return tokens


@dataclass(frozen=True)
class Chunk:
    """
    A searchable piece of a file.

    Attributes:
        path (str): Project-relative path.
        start_line (int): First line, 1-based.
        end_line (int): Last line, inclusive.
        text (str): The chunk's source text.
        symbols (Tuple[str, ...]): Names defined in the chunk.
    """

    path: str
    start_line: int
    end_line: int
    text: str
    symbols: Tuple[str, ...] = ()


@dataclass
class _IndexedFile:
    info: FileInfo
    content: str
    chunks: List[Chunk]
    term_counts: List[Counter]
    symbols: List[str]
    outline: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchHit:
    """A ranked chunk."""

    chunk: Chunk
    score: float


def _python_chunks(path: str, content: str) -> Optional[Tuple[List[Chunk], List[str]]]:
    """Chunks a Python file by top-level definition; None if it does not parse."""
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return None
    lines = content.split("\n")
    chunks: List[Chunk] = []
    outline: List[str] = []
    covered: Set[int] = set()

    def add(start: int, end: int, symbols: Tuple[str, ...]) -> None:
        end = min(end, len(lines))
        if end < start:
            return
        text = "\n".join(lines[start - 1 : end])
        if text.strip():
            chunks.append(Chunk(path, start, end, text, symbols))
        covered.update(range(start, end + 1))

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        end = node.end_lineno or node.lineno
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            outline.append(
                f"class {node.name}({bases})" if bases else f"class {node.name}"
            )
            methods = [
                n
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            for method in methods:
                outline.append(f"    def {method.name}({_signature(method)})")
            if end - start + 1 > _MAX_CHUNK_LINES and methods:
                first = min(
                    [methods[0].lineno] + [d.lineno for d in methods[0].decorator_list]
                )
                add(start, first - 1, (node.name,))
                for method in methods:
                    m_start = min(
                        [method.lineno] + [d.lineno for d in method.decorator_list]
                    )
                    add(
                        m_start,
                        method.end_lineno or method.lineno,
                        (node.name, method.name),
                    )
                covered.update(range(start, end + 1))
                continue
            add(start, end, (node.name,) + tuple(m.name for m in methods))
        else:
            outline.append(f"def {node.name}({_signature(node)})")
            add(start, end, (node.name,))

    # Module-level code between definitions (imports, constants, main block).
    run_start: Optional[int] = None
    for line_no in range(1, len(lines) + 2):
        inside = line_no <= len(lines) and line_no not in covered
        if inside and run_start is None:
            run_start = line_no
        elif not inside and run_start is not None:
            for window_start in range(run_start, line_no, _WINDOW_LINES):
                add(
                    window_start, min(window_start + _WINDOW_LINES - 1, line_no - 1), ()
                )
            run_start = None
    chunks.sort(key=lambda c: c.start_line)
    return chunks, outline


def _signature(node: ast.AST) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    names = [a.arg for a in node.args.posonlyargs + node.args.args]
    if node.args.vararg:
        names.append("*" + node.args.vararg.arg)
    names.extend(a.arg for a in node.args.kwonlyargs)
    if node.args.kwarg:
        names.append("**" + node.args.kwarg.arg)
    return ", ".join(names)


def _window_chunks(path: str, content: str) -> List[Chunk]:
    lines = content.split("\n")
    chunks: List[Chunk] = []
    start = 0
    while start < len(lines):
        end = min(start + _WINDOW_LINES, len(lines))
        text = "\n".join(lines[start:end])
        if text.strip():
            chunks.append(Chunk(path, start + 1, end, text))
        if end == len(lines):
            break
        start += _WINDOW_STEP
    return chunks


def _regex_outline(language: str, content: str) -> List[str]:
    names: List[str] = []
    for pattern in _SYMBOL_PATTERNS.get(language, ()):
        names.extend(pattern.findall(content))
    seen: Set[str] = set()
    ordered = []
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _build_file(info: FileInfo, content: str) -> _IndexedFile:
    language = _LANGUAGE_BY_SUFFIX.get(PurePosixPath(info.path).suffix.lower(), "")
    chunks: List[Chunk]
    outline: List[str]
    parsed = _python_chunks(info.path, content) if language == "python" else None
    if parsed is not None:
        chunks, outline = parsed
    else:
        chunks = _window_chunks(info.path, content)
        outline = _regex_outline(language, content) if language else []
    symbols = sorted(
        {s for c in chunks for s in c.symbols} | set(_outline_names(outline))
    )
    path_tokens = tokenize(info.path.replace("/", " ").replace(".", " "))
    term_counts = [
        Counter(tokenize(c.text) + path_tokens * 2 + [s.lower() for s in c.symbols] * 2)
        for c in chunks
    ]
    return _IndexedFile(info, content, chunks, term_counts, symbols, outline)


def _outline_names(outline: Iterable[str]) -> List[str]:
    names = []
    for entry in outline:
        match = re.match(r"\s*(?:class|def)\s+([A-Za-z_]\w*)", entry)
        names.append(match.group(1) if match else entry.strip())
    return names


class CodeIndex:
    """
    An incrementally refreshed BM25 index of one project.
    """

    def __init__(self, workspace: ProjectWorkspace) -> None:
        """
        Args:
            workspace (ProjectWorkspace): The project to index.
        """
        self.workspace = workspace
        self._files: Dict[str, _IndexedFile] = {}
        self._df: Counter = Counter()
        self._chunk_count = 0
        self._avg_len = 1.0
        self._lock = threading.Lock()

    def refresh(self) -> None:
        """Re-reads files that were added or changed and forgets deleted ones."""
        with self._lock:
            listing = {f.path: f for f in self.workspace.list_files()}
            changed = False
            for path in list(self._files):
                if path not in listing:
                    del self._files[path]
                    changed = True
            for path, info in listing.items():
                current = self._files.get(path)
                if current and (current.info.mtime, current.info.size) == (
                    info.mtime,
                    info.size,
                ):
                    continue
                content = self.workspace.read_text(path)
                if content is None:
                    self._files.pop(path, None)
                    continue
                self._files[path] = _build_file(info, content)
                changed = True
            if changed or not self._chunk_count:
                self._recompute_statistics()

    def _recompute_statistics(self) -> None:
        df: Counter = Counter()
        total_len = 0
        count = 0
        for indexed in self._files.values():
            for counts in indexed.term_counts:
                df.update(counts.keys())
                total_len += sum(counts.values())
                count += 1
        self._df = df
        self._chunk_count = count
        self._avg_len = total_len / count if count else 1.0

    # ── Queries ────────────────────────────────────────────────────────────

    def paths(self) -> List[str]:
        """Returns every indexed path, sorted."""
        with self._lock:
            return sorted(self._files)

    def content(self, path: str) -> Optional[str]:
        """Returns the indexed content of a file, or None."""
        with self._lock:
            indexed = self._files.get(path)
            return indexed.content if indexed else None

    def outline(self, path: str) -> List[str]:
        """Returns the top-level definitions of a file."""
        with self._lock:
            indexed = self._files.get(path)
            return list(indexed.outline) if indexed else []

    def search(
        self, query: str, limit: int = 20, boost_paths: Sequence[str] = ()
    ) -> List[SearchHit]:
        """
        Ranks chunks against a query.

        Args:
            query (str): Natural-language request or code.
            limit (int): Maximum hits returned.
            boost_paths (Sequence[str]): Paths the user referred to; their
                chunks rank higher.

        Returns:
            List[SearchHit]: Best chunks first.
        """
        terms = Counter(tokenize(query))
        if not terms and not boost_paths:
            return []
        boosted = set(boost_paths)
        with self._lock:
            n = max(1, self._chunk_count)
            hits: List[SearchHit] = []
            for path, indexed in self._files.items():
                for chunk, counts in zip(indexed.chunks, indexed.term_counts):
                    score = self._bm25(terms, counts, n)
                    lowered = {s.lower() for s in chunk.symbols}
                    for term in terms:
                        if term in lowered:
                            score += 2.0 * self._idf(term, n)
                    if path in boosted:
                        score += 5.0
                    if score > 0:
                        hits.append(SearchHit(chunk, score))
        hits.sort(key=lambda h: (-h.score, h.chunk.path, h.chunk.start_line))
        return hits[:limit]

    def rank_files(self, hits: Sequence[SearchHit]) -> List[str]:
        """Orders files by their best chunk, adding a share of their other hits."""
        scores: Dict[str, List[float]] = {}
        for hit in hits:
            scores.setdefault(hit.chunk.path, []).append(hit.score)
        ranked = sorted(
            scores.items(),
            key=lambda item: -(max(item[1]) + 0.3 * (sum(item[1]) - max(item[1]))),
        )
        return [path for path, _ in ranked]

    def find_paths(self, reference: str) -> List[str]:
        """
        Resolves a file reference the user typed (a path, a path suffix, or a
        bare file name) to indexed paths.

        Args:
            reference (str): What the user wrote, e.g. "service.py" or
                "developer/service.py".

        Returns:
            List[str]: Matching paths; exactly one when the reference is unambiguous.
        """
        ref = reference.strip().strip("`'\".,:;()[]").replace("\\", "/").lstrip("./")
        if not ref:
            return []
        with self._lock:
            if ref in self._files:
                return [ref]
            return sorted(p for p in self._files if p.endswith("/" + ref) or p == ref)

    def _idf(self, term: str, n: int) -> float:
        df = self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def _bm25(self, terms: Counter, counts: Counter, n: int) -> float:
        length = sum(counts.values()) or 1
        score = 0.0
        for term in terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            norm = (
                tf
                * (_BM25_K1 + 1)
                / (tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * length / self._avg_len))
            )
            score += self._idf(term, n) * norm
        return score


class IndexCache:
    """
    Keeps one CodeIndex per project folder so repeated requests only re-read
    files that changed.
    """

    def __init__(self, max_projects: int = 4) -> None:
        """
        Args:
            max_projects (int): Indexes kept in memory before the least
                recently used one is dropped.
        """
        self._max_projects = max_projects
        self._indexes: Dict[str, CodeIndex] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()

    def get(self, workspace: ProjectWorkspace) -> CodeIndex:
        """
        Returns the refreshed index for a workspace, creating it on first use.

        Args:
            workspace (ProjectWorkspace): The project.

        Returns:
            CodeIndex: An index reflecting the files currently on disk.
        """
        key = os.path.normcase(str(workspace.root))
        with self._lock:
            index = self._indexes.get(key)
            if index is None or index.workspace.max_files != workspace.max_files:
                index = CodeIndex(workspace)
                self._indexes[key] = index
            else:
                # Pick up a re-read .gitignore and current size limits.
                index.workspace = workspace
            if key in self._order:
                self._order.remove(key)
            self._order.append(key)
            while len(self._order) > self._max_projects:
                evicted = self._order.pop(0)
                self._indexes.pop(evicted, None)
        index.refresh()
        return index

    def forget(self, root: str) -> None:
        """Drops the index of a project folder."""
        key = os.path.normcase(str(root))
        with self._lock:
            self._indexes.pop(key, None)
            if key in self._order:
                self._order.remove(key)
