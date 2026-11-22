"""
Unified diff rendering for proposed file changes.
"""

import difflib
from typing import Optional

# A diff longer than this is cut short so a huge rewrite can't flood the UI;
# the full content is still what gets written when the change is applied.
_MAX_DIFF_LINES = 2000


def unified_diff(path: str, original: Optional[str], updated: str) -> str:
    """
    Renders a unified diff between two versions of a file.

    Args:
        path (str): Project-relative path, used in the diff header.
        original (Optional[str]): Content before; None for a new file.
        updated (str): Content after.

    Returns:
        str: The unified diff text (empty when nothing changed).
    """
    before = (original or "").splitlines(keepends=True)
    after = updated.splitlines(keepends=True)
    lines = list(
        difflib.unified_diff(
            before,
            after,
            fromfile="/dev/null" if original is None else f"a/{path}",
            tofile=f"b/{path}",
            n=3,
        )
    )
    normalized = [line if line.endswith("\n") else line + "\n" for line in lines]
    if len(normalized) > _MAX_DIFF_LINES:
        hidden = len(normalized) - _MAX_DIFF_LINES
        normalized = normalized[:_MAX_DIFF_LINES] + [
            f"... {hidden} more diff lines not shown ...\n"
        ]
    return "".join(normalized)
