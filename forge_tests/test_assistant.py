"""
Tests for the ForgeAI Assistant Plugin: workspace safety, code search, edit
parsing/applying, static change verification, the check runner, applying and
undoing changes, prompt building, and full assistant turns (driven by a
scripted model) including retries, auto-fix rounds and cancellation.
"""

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from unittest.mock import MagicMock

from forge_core.configuration.models import ModelSettings
from forge_core.configuration.service import ConfigurationService
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.model_router.exceptions import GenerationError
from forge_core.model_router.service import (
    ChatChunk,
    ModelProvider,
    ModelResponse,
    ModelRouterService,
)
from forge_plugins.assistant.components.agent import (
    AssistantAgent,
    Prompts,
    format_check_failure,
    should_reproduce,
    summarize_plan,
)
from forge_plugins.assistant.components.change_applier import ChangeApplier
from forge_plugins.assistant.components.change_verifier import (
    ChangeVerifier,
    missing_self_attributes,
)
from forge_plugins.assistant.components.check_runner import CheckRunner, split_command
from forge_plugins.assistant.components.code_index import (
    CodeIndex,
    IndexCache,
    tokenize,
)
from forge_plugins.assistant.components.context_builder import (
    ContextBuilder,
    estimate_tokens,
    find_referenced_paths,
)
from forge_plugins.assistant.components.edit_blocks import (
    apply_edit_blocks,
    parse_edit_blocks,
    replace_once,
    whole_file_edits,
)
from forge_plugins.assistant.components.snippet_edits import definition_edits
from forge_plugins.assistant.components.workspace import (
    ProjectWorkspace,
    validate_project_root,
)
from forge_plugins.assistant.exceptions import (
    AssistantError,
    ChangeConflictError,
    ChangeSetStateError,
    ConversationBusyError,
    ConversationNotFoundError,
    InvalidProjectError,
    UnsafePathError,
)
from forge_plugins.assistant.models import (
    AssistantMode,
    AssistantSettings,
    ChangeSet,
    ChangeSetStatus,
    Conversation,
    FileChange,
    Message,
    MessageRole,
)
from forge_plugins.assistant.service import ForgeAIAssistant
from forge_plugins.assistant.store import SQLiteAssistantStore

PROMPTS = Prompts(ask="ASK SYSTEM", edit="EDIT SYSTEM")

STORE_PY = '''"""Task storage."""

from typing import List


class TaskStore:
    def __init__(self) -> None:
        self._tasks: List[str] = []

    def add(self, title: str) -> None:
        self._tasks.append(title)

    def list(self) -> List[str]:
        return list(self._tasks)
'''

CLI_PY = """from todo.store import TaskStore


def main() -> None:
    store = TaskStore()
    store.add("x")
    print(store.list())
"""

ADD_COUNT_REPLY = """Add a count method.

todo/store.py
<<<<<<< SEARCH
    def list(self) -> List[str]:
        return list(self._tasks)
=======
    def list(self) -> List[str]:
        return list(self._tasks)

    def count(self) -> int:
        return len(self._tasks)
>>>>>>> REPLACE
"""


def write_project(root: Path, files: Dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class ScriptedRouter(ModelRouterService):
    """Model router test double that replays scripted replies in order."""

    def __init__(self, replies: List[str], fail_with: Optional[str] = None) -> None:
        self.replies = list(replies)
        self.calls: List[List[Dict[str, str]]] = []
        self.kwargs: List[Dict[str, Any]] = []
        self.fail_with = fail_with
        self.on_chunk: Optional[Any] = None

    def register_provider(self, provider: ModelProvider) -> None:
        raise NotImplementedError

    def get_provider(self, name: str) -> ModelProvider:
        raise NotImplementedError

    def generate(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        raise NotImplementedError

    def generate_chat(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        raise NotImplementedError

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Iterator[ChatChunk]:
        self.calls.append(messages)
        self.kwargs.append(kwargs)
        if self.fail_with:
            raise GenerationError(self.fail_with)
        reply = self.replies.pop(0) if self.replies else "No more replies."

        def chunks() -> Iterator[ChatChunk]:
            for i in range(0, len(reply), 7):
                if self.on_chunk:
                    self.on_chunk()
                yield ChatChunk(text=reply[i : i + 7])
            yield ChatChunk(text="", done=True, usage={"completion_tokens": 5})

        return chunks()


class TempProjectCase(unittest.TestCase):
    """Base case with a temporary project folder."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "proj"
        self.root.mkdir()
        write_project(
            self.root,
            {"todo/__init__.py": "", "todo/store.py": STORE_PY, "todo/cli.py": CLI_PY},
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def workspace(self) -> ProjectWorkspace:
        return ProjectWorkspace(str(self.root), 4000, 262144)


# ── Streaming in the model router ──────────────────────────────────────────


class FakeStreamResponse:
    def __init__(self, lines: List[bytes]) -> None:
        self.lines = lines

    def __iter__(self) -> Iterator[bytes]:
        return iter(self.lines)

    def __enter__(self) -> "FakeStreamResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        return None


class TestStreaming(unittest.TestCase):
    def test_ollama_stream_yields_text_then_usage(self) -> None:
        from unittest.mock import patch

        from forge_core.model_router.providers import OllamaProvider

        lines = [
            b'{"message": {"content": "Hel"}, "done": false}\n',
            b'{"message": {"content": "lo"}, "done": false}\n',
            b'{"message": {"content": ""}, "done": true, "prompt_eval_count": 3, "eval_count": 2}\n',
        ]
        provider = OllamaProvider("http://localhost:11434", "m", keep_alive="2m")
        with patch(
            "urllib.request.urlopen", return_value=FakeStreamResponse(lines)
        ) as urlopen:
            chunks = list(
                provider.stream_chat(
                    [{"role": "user", "content": "hi"}], options={"num_ctx": 8192}
                )
            )
        self.assertEqual("".join(c.text for c in chunks), "Hello")
        self.assertTrue(chunks[-1].done)
        self.assertEqual(chunks[-1].usage["total_tokens"], 5)
        import json

        payload = json.loads(urlopen.call_args[0][0].data)
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["options"]["num_ctx"], 8192)
        self.assertEqual(payload["keep_alive"], "2m")

    def test_ollama_stream_error_event_raises(self) -> None:
        from unittest.mock import patch

        from forge_core.model_router.providers import OllamaProvider

        provider = OllamaProvider("http://localhost:11434", "m")
        with patch(
            "urllib.request.urlopen",
            return_value=FakeStreamResponse([b'{"error": "model not found"}\n']),
        ):
            with self.assertRaises(GenerationError):
                list(provider.stream_chat([{"role": "user", "content": "hi"}]))

    def test_ollama_stream_closed_early_raises(self) -> None:
        from unittest.mock import patch

        from forge_core.model_router.providers import OllamaProvider

        provider = OllamaProvider("http://localhost:11434", "m")
        with patch(
            "urllib.request.urlopen",
            return_value=FakeStreamResponse(
                [b'{"message": {"content": "a"}, "done": false}\n']
            ),
        ):
            with self.assertRaises(GenerationError):
                list(provider.stream_chat([{"role": "user", "content": "hi"}]))

    def test_openai_compatible_sse_stream(self) -> None:
        from unittest.mock import patch

        from forge_core.model_router.providers import OpenAICompatibleProvider

        lines = [
            b'data: {"choices": [{"delta": {"content": "Hi"}}]}\n',
            b": keep-alive\n",
            b'data: {"choices": [{"delta": {"content": " there"}, "finish_reason": "stop"}]}\n',
            b"data: [DONE]\n",
        ]
        provider = OpenAICompatibleProvider("http://localhost:1234/v1", "m")
        with patch("urllib.request.urlopen", return_value=FakeStreamResponse(lines)):
            chunks = list(provider.stream_chat([{"role": "user", "content": "hi"}]))
        self.assertEqual("".join(c.text for c in chunks), "Hi there")
        self.assertTrue(chunks[-1].done)

    def test_default_stream_falls_back_to_generate_chat(self) -> None:
        class Plain(ModelProvider):
            @property
            def name(self) -> str:
                return "plain"

            def generate(
                self, prompt: str, model: Optional[str] = None, **kwargs: Any
            ) -> ModelResponse:
                raise NotImplementedError

            def generate_chat(
                self,
                messages: List[Dict[str, str]],
                model: Optional[str] = None,
                **kwargs: Any,
            ) -> ModelResponse:
                return ModelResponse("whole reply", {}, "m", {"total_tokens": 4})

        chunks = list(Plain().stream_chat([]))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "whole reply")
        self.assertTrue(chunks[0].done)

    def test_router_routes_stream_to_provider_with_defaults(self) -> None:
        from forge_core.model_router.router import ModelRouter

        config = MagicMock(spec=ConfigurationService)
        config.get_model_settings.return_value = ModelSettings(
            provider="ollama",
            default_model="m",
            base_url="http://localhost:11434",
            temperature=0.5,
            max_tokens=99,
        )
        router = ModelRouter(config)
        provider = MagicMock(spec=ModelProvider)
        provider.name = "ollama"
        provider.stream_chat.return_value = iter([ChatChunk("x", done=True)])
        router.register_provider(provider)
        list(router.stream_chat([{"role": "user", "content": "q"}], max_tokens=10))
        kwargs = provider.stream_chat.call_args.kwargs
        self.assertEqual(kwargs["max_tokens"], 10)
        self.assertEqual(kwargs["temperature"], 0.5)


# ── Workspace ──────────────────────────────────────────────────────────────


class TestWorkspace(TempProjectCase):
    def test_normalize_rejects_unsafe_paths(self) -> None:
        ws = self.workspace()
        for bad in [
            "../outside.py",
            "/etc/passwd",
            "C:\\Windows\\x.py",
            ".git/config",
            "node_modules/a/b.js",
            "",
        ]:
            with self.assertRaises(UnsafePathError, msg=bad):
                ws.normalize(bad)
        self.assertEqual(ws.normalize("./todo\\store.py"), "todo/store.py")

    def test_list_files_skips_ignored_binary_and_large(self) -> None:
        write_project(
            self.root,
            {
                ".gitignore": "secret/\n*.log\n!keep.log\n",
                "secret/key.py": "x = 1\n",
                "node_modules/lib/index.js": "x",
                "app.log": "log",
                "keep.log": "kept",
                "package-lock.json": "{}",
                "big.py": "x = 1\n" * 100000,
            },
        )
        (self.root / "image.png").write_bytes(b"\x89PNG\x00\x00")
        (self.root / "data.txt").write_bytes(b"abc\x00def")
        paths = [
            f.path for f in ProjectWorkspace(str(self.root), 4000, 65536).list_files()
        ]
        self.assertIn("todo/store.py", paths)
        self.assertIn(".gitignore", paths)
        for skipped in [
            "secret/key.py",
            "node_modules/lib/index.js",
            "app.log",
            "package-lock.json",
            "big.py",
            "image.png",
        ]:
            self.assertNotIn(skipped, paths)
        self.assertIsNone(self.workspace().read_text("data.txt"))

    def test_list_files_respects_max_files(self) -> None:
        write_project(self.root, {f"many/f{i}.py": "" for i in range(30)})
        self.assertEqual(
            len(ProjectWorkspace(str(self.root), 10, 65536).list_files()), 10
        )

    def test_write_preserves_crlf_and_creates_folders(self) -> None:
        ws = self.workspace()
        (self.root / "win.py").write_bytes(b"a = 1\r\nb = 2\r\n")
        self.assertEqual(ws.read_text("win.py"), "a = 1\nb = 2\n")
        ws.write_text("win.py", "a = 1\nb = 3\n")
        self.assertEqual((self.root / "win.py").read_bytes(), b"a = 1\r\nb = 3\r\n")
        ws.write_text("new/dir/mod.py", "x = 1\n")
        self.assertEqual((self.root / "new/dir/mod.py").read_text(), "x = 1\n")
        self.assertFalse(
            any(p.name.startswith(".forge-") for p in self.root.rglob("*"))
        )

    def test_validate_project_root(self) -> None:
        with self.assertRaises(InvalidProjectError):
            validate_project_root(str(self.root / "missing"))
        with self.assertRaises(InvalidProjectError):
            validate_project_root(str(self.root / "todo" / "store.py"))
        with self.assertRaises(InvalidProjectError):
            validate_project_root(Path(self.root.anchor).as_posix())
        with self.assertRaises(InvalidProjectError):
            validate_project_root(str(Path.home()))
        with self.assertRaises(InvalidProjectError):
            validate_project_root("  ")
        self.assertEqual(validate_project_root(str(self.root)), self.root.resolve())


# ── Code index ─────────────────────────────────────────────────────────────


class TestCodeIndex(TempProjectCase):
    def test_tokenize_splits_identifiers(self) -> None:
        tokens = tokenize("loadTasks load_tasks HTTPServer")
        for expected in ["loadtasks", "load", "tasks", "load_tasks", "http", "server"]:
            self.assertIn(expected, tokens)
        self.assertNotIn("the", tokenize("the"))

    def test_search_ranks_defining_file_first(self) -> None:
        index = CodeIndex(self.workspace())
        index.refresh()
        hits = index.search("how are tasks added to the TaskStore")
        self.assertEqual(hits[0].chunk.path, "todo/store.py")
        self.assertIn("TaskStore", index.outline("todo/store.py")[0])

    def test_refresh_picks_up_changes_and_deletions(self) -> None:
        index = CodeIndex(self.workspace())
        index.refresh()
        write_project(self.root, {"todo/extra.py": "def frobnicate():\n    return 1\n"})
        index.refresh()
        self.assertEqual(index.search("frobnicate")[0].chunk.path, "todo/extra.py")
        (self.root / "todo/extra.py").unlink()
        index.refresh()
        self.assertNotIn("todo/extra.py", index.paths())

    def test_find_paths_by_suffix(self) -> None:
        index = CodeIndex(self.workspace())
        index.refresh()
        self.assertEqual(index.find_paths("store.py"), ["todo/store.py"])
        self.assertEqual(index.find_paths("@todo/cli.py".lstrip("@")), ["todo/cli.py"])
        self.assertEqual(index.find_paths("nothing.py"), [])

    def test_index_cache_reuses_index(self) -> None:
        cache = IndexCache(max_projects=1)
        first = cache.get(self.workspace())
        self.assertIs(cache.get(self.workspace()), first)


# ── Edit blocks ────────────────────────────────────────────────────────────


class TestEditBlocks(unittest.TestCase):
    def test_parse_tolerates_fences_and_decorated_paths(self) -> None:
        reply = (
            "Plan.\n\n```python\n**app/a.py**\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n```\n"
            "<<<<<<< SEARCH\ny = 1\n=======\ny = 2\n>>>>>>> REPLACE\n"
            "File: `app/b.py`\n<<<<<<<< SEARCH\n========\nz = 1\n>>>>>>>> REPLACE\n"
        )
        parsed = parse_edit_blocks(reply)
        self.assertEqual(
            [b.path for b in parsed.blocks], ["app/a.py", "app/a.py", "app/b.py"]
        )
        self.assertEqual(parsed.blocks[2].search, "")
        self.assertEqual(parsed.problems, [])

    def test_parse_reports_malformed_blocks(self) -> None:
        cut_off = parse_edit_blocks("a.py\n<<<<<<< SEARCH\nx\n=======\ny\n")
        self.assertIn("length limit", cut_off.problems[0].message)
        no_divider = parse_edit_blocks("a.py\n<<<<<<< SEARCH\nx\n>>>>>>> REPLACE\n")
        self.assertIn("=======", no_divider.problems[0].message)
        no_path = parse_edit_blocks("<<<<<<< SEARCH\nx\n=======\ny\n>>>>>>> REPLACE\n")
        self.assertIn("no file path", no_path.problems[0].message)
        self.assertFalse(parse_edit_blocks("just an answer").found_any)

    def test_replace_strategies(self) -> None:
        content = "class A:\n    def f(self):\n        return 1   \n\n\n    def g(self):\n        return 2\n"
        exact, problem = replace_once(
            content,
            "    def g(self):\n        return 2",
            "    def g(self):\n        return 3",
        )
        self.assertIsNone(problem)
        self.assertIn("return 3", exact)
        trailing, problem = replace_once(
            content, "        return 1", "        return 10"
        )
        self.assertIsNone(problem)
        self.assertIn("return 10", trailing)
        dedented, problem = replace_once(
            content, "def g(self):\n    return 2", "def g(self):\n    return 4"
        )
        self.assertIsNone(problem)
        self.assertIn("    def g(self):\n        return 4", dedented)
        no_blank, problem = replace_once(
            content,
            "        return 1\n    def g(self):",
            "        return 5\n    def g(self):",
        )
        self.assertIsNone(problem)
        self.assertIn("return 5", no_blank)

    def test_replace_reports_ambiguous_and_missing(self) -> None:
        content = "x = 1\nx = 1\ny = 2\n"
        _, ambiguous = replace_once(content, "x = 1", "x = 3")
        assert ambiguous is not None
        self.assertIn("matches 2 places", ambiguous[0])
        _, missing = replace_once(content, "y = 22", "y = 3")
        assert missing is not None
        self.assertIn("does not match", missing[0])
        self.assertIn("closest lines", missing[1])

    def test_apply_creates_files_and_rejects_elisions(self) -> None:
        files = {"a.py": "def f():\n    return 1\n"}
        blocks = parse_edit_blocks(
            "new.py\n<<<<<<< SEARCH\n=======\nprint('hi')\n>>>>>>> REPLACE\n"
            "a.py\n<<<<<<< SEARCH\ndef f():\n    return 1\n=======\ndef f():\n    # ... rest of the code ...\n>>>>>>> REPLACE\n"
            "a.py\n<<<<<<< SEARCH\n=======\nx = 1\n>>>>>>> REPLACE\n"
            "missing.py\n<<<<<<< SEARCH\nx\n=======\ny\n>>>>>>> REPLACE\n"
        ).blocks
        changes, problems = apply_edit_blocks(blocks, files.get, lambda p: p)
        self.assertEqual([c.path for c in changes], ["new.py"])
        self.assertIsNone(changes[0].original)
        self.assertEqual(changes[0].updated, "print('hi')\n")
        messages = " ".join(p.message for p in problems)
        self.assertIn("instead of real code", messages)
        self.assertIn("already exists", messages)
        self.assertIn("does not exist", messages)

    def test_no_op_blocks_are_skipped(self) -> None:
        files = {"a.py": "x = 1\n", "b.py": "y = 1\n"}
        blocks = parse_edit_blocks(
            "a.py\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n"
            "b.py\n<<<<<<< SEARCH\ny = 1\n=======\ny = 1\n>>>>>>> REPLACE\n"
        ).blocks
        changes, problems = apply_edit_blocks(blocks, files.get, lambda p: p)
        self.assertEqual(problems, [])
        self.assertEqual([c.path for c in changes], ["a.py"])

    def test_apply_reports_unsafe_paths(self) -> None:
        def normalize(path: str) -> str:
            raise UnsafePathError("outside")

        _, problems = apply_edit_blocks(
            parse_edit_blocks(ADD_COUNT_REPLY).blocks, lambda p: STORE_PY, normalize
        )
        self.assertEqual(problems[0].message, "outside")

    def test_whole_file_edits(self) -> None:
        files = {"todo/store.py": STORE_PY}
        new = (
            STORE_PY
            + "\n    def count(self) -> int:\n        return len(self._tasks)\n"
        )
        reply = f"### todo/store.py (whole file)\n```python\n{new}```\n"
        changes = whole_file_edits(reply, ["todo/store.py"], files.get, lambda p: p)
        self.assertEqual(changes[0].updated, new)
        # No path given: inferred from content.
        self.assertEqual(
            len(
                whole_file_edits(
                    f"```python\n{new}```", ["todo/store.py"], files.get, lambda p: p
                )
            ),
            1,
        )
        # Dropping an existing definition is refused.
        partial = "### todo/store.py\n```python\ndef other():\n    pass\n```\n"
        self.assertEqual(
            whole_file_edits(partial, ["todo/store.py"], files.get, lambda p: p), []
        )
        # Files that were not shown in full are never replaced.
        self.assertEqual(whole_file_edits(reply, [], files.get, lambda p: p), [])
        # Regression: a block with only the class must not replace the whole
        # file, which would drop its docstring and imports.
        class_only = "```python\n" + STORE_PY.split("\n\n\n", 1)[1] + "```"
        self.assertEqual(
            whole_file_edits(class_only, ["todo/store.py"], files.get, lambda p: p), []
        )

    def test_definition_edits(self) -> None:
        files = {"todo/store.py": STORE_PY}
        reply = (
            "```python\nfrom typing import Dict\n\n\nclass TaskStore:\n    def __init__(self) -> None:\n"
            "        self._tasks: List[str] = []\n\n    def add(self, title: str) -> None:\n"
            "        self._tasks.append(title)\n\n    def list(self) -> List[str]:\n"
            "        return list(self._tasks)\n\n    def count(self) -> int:\n        return len(self._tasks)\n\n\n"
            "def helper() -> Dict[str, int]:\n    return {}\n```"
        )
        changes = definition_edits(reply, ["todo/store.py"], files.get, lambda p: p)
        updated = changes[0].updated
        self.assertIn("def count(self) -> int:", updated)
        self.assertIn('"""Task storage."""', updated)
        self.assertIn("from typing import Dict", updated)
        self.assertTrue(updated.rstrip().endswith("return {}"))
        compile(updated, "store.py", "exec")
        # A restated class that drops a method is refused.
        dropped = (
            "```python\nclass TaskStore:\n    def add(self, title):\n        pass\n```"
        )
        self.assertEqual(
            definition_edits(dropped, ["todo/store.py"], files.get, lambda p: p), []
        )
        # Other statements make the block unusable.
        self.assertEqual(
            definition_edits(
                "```python\nprint(1)\n```", ["todo/store.py"], files.get, lambda p: p
            ),
            [],
        )


# ── Verification ───────────────────────────────────────────────────────────


class TestChangeVerifier(TempProjectCase):
    def test_change_breaking_another_file_is_reported(self) -> None:
        index = CodeIndex(self.workspace())
        index.refresh()
        renamed = STORE_PY.replace("class TaskStore", "class Store")
        result = ChangeVerifier().verify(
            index, [FileChange("todo/store.py", STORE_PY, renamed)]
        )
        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                i.path == "todo/cli.py" and "TaskStore" in i.message
                for i in result.errors
            )
        )

    def test_pre_existing_problems_are_not_blamed_on_the_change(self) -> None:
        write_project(
            self.root,
            {"broken.py": "from nowhere_local import x\nprint(undefined_name)\n"},
        )
        index = CodeIndex(self.workspace())
        index.refresh()
        updated = STORE_PY + "\n\nVERSION = 1\n"
        result = ChangeVerifier().verify(
            index, [FileChange("todo/store.py", STORE_PY, updated)]
        )
        self.assertTrue(result.passed, result.to_dict())

    def test_syntax_error_and_missing_method_detected(self) -> None:
        index = CodeIndex(self.workspace())
        index.refresh()
        broken = STORE_PY.replace("return list(self._tasks)", "return list(self._tasks")
        self.assertEqual(
            ChangeVerifier()
            .verify(index, [FileChange("todo/store.py", STORE_PY, broken)])
            .errors[0]
            .check,
            "syntax",
        )
        uses_missing = (
            STORE_PY + "\n    def first(self) -> str:\n        return self._lookup(0)\n"
        )
        result = ChangeVerifier().verify(
            index, [FileChange("todo/store.py", STORE_PY, uses_missing)]
        )
        self.assertEqual(result.errors[0].check, "attribute")
        self.assertIn("_lookup", result.errors[0].message)

    def test_non_python_change_is_not_checked(self) -> None:
        index = CodeIndex(self.workspace())
        index.refresh()
        result = ChangeVerifier().verify(
            index, [FileChange("README.md", None, "# hi\n")]
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.checked_files, 0)
        self.assertIn("nothing", result.skipped_reason)

    def test_missing_self_attributes_is_conservative(self) -> None:
        source = (
            "class Base:\n    pass\n\n"
            "class Known(Base):\n    x = 1\n    def __init__(self):\n        self.y = 2\n"
            "    def f(self):\n        return self.x + self.y + self.g() + self.missing\n"
            "    def g(self):\n        return self.__class__\n\n"
            "class External(dict):\n    def f(self):\n        return self.anything\n\n"
            "class Dynamic:\n    def __getattr__(self, name):\n        return 1\n    def f(self):\n        return self.anything\n"
        )
        found = missing_self_attributes(source)
        self.assertEqual(len(found), 1)
        self.assertIn("self.missing", found[0][0])
        self.assertEqual(missing_self_attributes("def broken(:"), [])


# ── Check runner ───────────────────────────────────────────────────────────


class TestCheckRunner(TempProjectCase):
    def test_passing_and_failing_commands(self) -> None:
        runner = CheckRunner()
        python = f'"{sys.executable}"'
        passed = runner.run(f"{python} -c \"print('ok')\"", self.root, 60)
        self.assertTrue(passed.passed)
        self.assertIn("ok", passed.output)
        failed = runner.run(
            f"{python} -c \"import sys; print('bad'); sys.exit(3)\"", self.root, 60
        )
        self.assertFalse(failed.passed)
        self.assertEqual(failed.exit_code, 3)
        self.assertIn("bad", failed.output)

    def test_runs_in_project_folder(self) -> None:
        result = CheckRunner().run(
            f'"{sys.executable}" -c "import os; print(os.getcwd())"', self.root, 60
        )
        self.assertEqual(Path(result.output.strip()).resolve(), self.root.resolve())

    def test_missing_executable_and_bad_quotes(self) -> None:
        missing = CheckRunner().run("definitely-not-a-real-tool --x", self.root, 10)
        self.assertFalse(missing.passed)
        self.assertIn("not found", missing.error)
        self.assertIn("empty", CheckRunner().run("   ", self.root, 10).error)

    def test_timeout_stops_the_command(self) -> None:
        result = CheckRunner().run(
            f'"{sys.executable}" -c "import time; time.sleep(30)"', self.root, 1
        )
        self.assertTrue(result.timed_out)
        self.assertFalse(result.passed)
        self.assertLess(result.duration_seconds, 25)

    def test_output_is_trimmed(self) -> None:
        result = CheckRunner().run(
            f'"{sys.executable}" -c "print(\'x\' * 20000)"', self.root, 60
        )
        self.assertIn("characters of output not shown", result.output)

    def test_split_command(self) -> None:
        self.assertEqual(
            split_command('python -m pytest "tests/a b.py" -q'),
            ["python", "-m", "pytest", "tests/a b.py", "-q"],
        )
        with self.assertRaises(ValueError):
            split_command("")


# ── Applying and undoing ───────────────────────────────────────────────────


def make_change_set(
    files: List[FileChange], status: ChangeSetStatus = ChangeSetStatus.PENDING
) -> ChangeSet:
    return ChangeSet("cs1", "c1", "m1", status, "summary", files, None, None, 1.0, 1.0)


class TestChangeApplier(TempProjectCase):
    def test_apply_and_revert_round_trip(self) -> None:
        ws = self.workspace()
        updated = STORE_PY.replace("str", "object")
        change = make_change_set(
            [
                FileChange("todo/store.py", STORE_PY, updated),
                FileChange("todo/new.py", None, "x = 1\n"),
            ]
        )
        ChangeApplier().apply(ws, change)
        self.assertEqual(ws.read_text("todo/store.py"), updated)
        self.assertTrue(ws.exists("todo/new.py"))
        ChangeApplier().revert(ws, change)
        self.assertEqual(ws.read_text("todo/store.py"), STORE_PY)
        self.assertFalse(ws.exists("todo/new.py"))

    def test_apply_refuses_when_file_changed_since_proposal(self) -> None:
        ws = self.workspace()
        change = make_change_set(
            [FileChange("todo/store.py", "something else\n", "new\n")]
        )
        with self.assertRaises(ChangeConflictError):
            ChangeApplier().apply(ws, change)
        self.assertEqual(ws.read_text("todo/store.py"), STORE_PY)

    def test_revert_refuses_when_file_edited_after_apply(self) -> None:
        ws = self.workspace()
        change = make_change_set([FileChange("todo/store.py", STORE_PY, "new\n")])
        ChangeApplier().apply(ws, change)
        ws.write_text("todo/store.py", "user edit\n")
        with self.assertRaises(ChangeConflictError):
            ChangeApplier().revert(ws, change)

    def test_failed_write_restores_earlier_files(self) -> None:
        ws = self.workspace()
        change = make_change_set(
            [
                FileChange("todo/store.py", STORE_PY, "new\n"),
                FileChange("todo/cli.py", CLI_PY, "new cli\n"),
            ]
        )
        original_write = ws.write_text

        def flaky(path: str, content: str) -> None:
            if path == "todo/cli.py" and content == "new cli\n":
                raise OSError("disk full")
            original_write(path, content)

        ws.write_text = flaky  # type: ignore[method-assign]
        with self.assertRaises(OSError):
            ChangeApplier().apply(ws, change)
        self.assertEqual(ws.read_text("todo/store.py"), STORE_PY)


# ── Prompt building ────────────────────────────────────────────────────────


def message(
    role: MessageRole,
    content: str,
    mode: AssistantMode = AssistantMode.ASK,
    **metadata: Any,
) -> Message:
    return Message(content[:8] + role.value, "c1", role, mode, content, metadata, 1.0)


class TestContextBuilder(TempProjectCase):
    def build(self, request: str, mode: AssistantMode = AssistantMode.EDIT, history: Optional[List[Message]] = None, context_tokens: int = 8192, change_sets: Optional[Dict[str, ChangeSet]] = None):  # type: ignore[no-untyped-def]
        index = CodeIndex(self.workspace())
        index.refresh()
        return ContextBuilder(context_tokens).build(
            mode=mode,
            system_prompt="SYSTEM",
            request=request,
            index=index,
            project_name="proj",
            history=history or [],
            change_sets=change_sets or {},
            output_tokens=1024,
        )

    def test_edit_mode_shows_whole_relevant_files(self) -> None:
        context = self.build("add a count method to TaskStore in @store.py")
        self.assertEqual(context.referenced_paths, ["todo/store.py"])
        self.assertTrue(context.included[0].full)
        self.assertEqual(context.included[0].path, "todo/store.py")
        final = context.messages[-1]["content"]
        self.assertIn("## Code you can edit", final)
        self.assertIn("### todo/store.py (whole file)", final)
        self.assertTrue(
            final.rstrip().endswith("add a count method to TaskStore in @store.py")
        )

    def test_budget_is_respected(self) -> None:
        write_project(
            self.root,
            {
                f"pkg/m{i}.py": f"def task_function_{i}():\n"
                + "    x = 'task store'\n" * 200
                for i in range(10)
            },
        )
        context = self.build(
            "task store functions", mode=AssistantMode.ASK, context_tokens=3000
        )
        self.assertLessEqual(context.prompt_tokens, 3000 - 1024)

    def test_history_drops_code_failed_edits_and_repeats(self) -> None:
        history = [
            message(MessageRole.USER, "why is it slow?"),
            message(
                MessageRole.ASSISTANT,
                "Because of X.\n```python\nprint('old code')\n```\nThat is all.",
            ),
            message(MessageRole.USER, "add count"),
            message(MessageRole.ASSISTANT, "garbage", AssistantMode.EDIT),
            message(
                MessageRole.CHECK,
                "failed",
                AssistantMode.EDIT,
                check={
                    "command": "pytest",
                    "passed": False,
                    "output": "E  AssertionError",
                },
            ),
        ]
        context = self.build("add count", history=history)
        rendered = [m["content"] for m in context.messages[1:-1]]
        joined = "\n".join(rendered)
        self.assertIn("Because of X.", joined)
        self.assertNotIn("old code", joined)
        self.assertNotIn("garbage", joined)
        self.assertNotIn("add count", joined)
        self.assertIn("AssertionError", joined)

    def test_applied_change_is_summarized_in_history(self) -> None:
        cs = make_change_set(
            [FileChange("todo/store.py", STORE_PY, STORE_PY + "\n")],
            ChangeSetStatus.APPLIED,
        )
        history = [
            message(MessageRole.USER, "add count"),
            message(
                MessageRole.ASSISTANT,
                ADD_COUNT_REPLY,
                AssistantMode.EDIT,
                change_set_id="cs1",
            ),
        ]
        context = self.build("now add remove", history=history, change_sets={"cs1": cs})
        assistant = [m for m in context.messages if m["role"] == "assistant"][0][
            "content"
        ]
        self.assertIn("Add a count method.", assistant)
        self.assertIn("the user applied them", assistant)
        self.assertNotIn("SEARCH", assistant)

    def test_traceback_paths_are_referenced(self) -> None:
        index = CodeIndex(self.workspace())
        index.refresh()
        traceback = (
            'File "C:\\work\\proj\\todo\\store.py", line 9, in add\nAttributeError'
        )
        self.assertEqual(find_referenced_paths(traceback, index), ["todo/store.py"])

    def test_estimate_tokens_is_conservative(self) -> None:
        self.assertGreaterEqual(estimate_tokens("x" * 300), 100)


# ── Agent turns ────────────────────────────────────────────────────────────


class AgentCase(TempProjectCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = SQLiteAssistantStore(":memory:")
        self.store.initialize()
        self.conversation = Conversation("c1", "", str(self.root), "", False, 1.0, 1.0)
        self.store.save_conversation(self.conversation)

    def tearDown(self) -> None:
        self.store.close()
        super().tearDown()

    def agent(self, router: ScriptedRouter, **settings: Any) -> AssistantAgent:
        return AssistantAgent(
            router, self.store, AssistantSettings(**settings), PROMPTS
        )

    def run_turn(
        self,
        router: ScriptedRouter,
        text: str,
        mode: AssistantMode,
        conversation: Optional[Conversation] = None,
        cancel: Optional[threading.Event] = None,
        **settings: Any,
    ) -> List[Dict[str, Any]]:
        return list(
            self.agent(router, **settings).run_turn(
                conversation or self.conversation,
                text,
                mode,
                [],
                cancel or threading.Event(),
            )
        )


class TestAgentAsk(AgentCase):
    def test_answer_is_streamed_and_stored(self) -> None:
        router = ScriptedRouter(["TaskStore keeps titles in a list."])
        events = self.run_turn(router, "where are tasks kept?", AssistantMode.ASK)
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "message")
        self.assertIn("context", types)
        self.assertIn("token", types)
        self.assertEqual(types[-1], "done")
        self.assertEqual(
            "".join(e["text"] for e in events if e["type"] == "token"),
            "TaskStore keeps titles in a list.",
        )
        stored = self.store.list_messages("c1")
        self.assertEqual(
            [m.role for m in stored], [MessageRole.USER, MessageRole.ASSISTANT]
        )
        self.assertEqual(stored[1].metadata["usage"], {"completion_tokens": 5})
        self.assertEqual(router.calls[0][0]["content"], "ASK SYSTEM")
        self.assertEqual(router.kwargs[0]["options"], {"num_ctx": 8192})

    def test_model_failure_is_reported_and_stored(self) -> None:
        events = self.run_turn(
            ScriptedRouter([], fail_with="connection refused"), "hi", AssistantMode.ASK
        )
        errors = [e for e in events if e["type"] == "error"]
        self.assertIn("connection refused", errors[0]["detail"])
        self.assertIn("error", self.store.list_messages("c1")[-1].metadata)

    def test_cancel_stops_generation_and_keeps_partial_reply(self) -> None:
        cancel = threading.Event()
        router = ScriptedRouter(["a long reply that will be cut off part way through"])
        calls = {"n": 0}

        def stop_after_two() -> None:
            calls["n"] += 1
            if calls["n"] == 3:
                cancel.set()

        router.on_chunk = stop_after_two
        self.run_turn(router, "hi", AssistantMode.ASK, cancel=cancel)
        reply = self.store.list_messages("c1")[-1]
        self.assertTrue(reply.metadata["cancelled"])
        self.assertEqual(reply.content, "a long reply t")

    def test_reproduce_runs_check_before_answering(self) -> None:
        conversation = Conversation(
            "c1",
            "",
            str(self.root),
            f'"{sys.executable}" -c "raise SystemExit(\'boom-marker\')"',
            False,
            1.0,
            1.0,
        )
        router = ScriptedRouter(["It fails because of boom."])
        events = self.run_turn(
            router,
            "why do the tests fail?",
            AssistantMode.ASK,
            conversation=conversation,
        )
        roles = [e["message"]["role"] for e in events if e["type"] == "message"]
        self.assertEqual(roles, ["user", "check", "assistant"])
        self.assertIn("boom-marker", router.calls[0][-1]["content"])
        self.assertFalse(should_reproduce(conversation, "add a flag", []))
        self.assertFalse(should_reproduce(conversation, "it fails:\n```\nlog\n```", []))


class TestAgentEdit(AgentCase):
    def test_edit_creates_pending_change_set(self) -> None:
        events = self.run_turn(
            ScriptedRouter([ADD_COUNT_REPLY]), "add count", AssistantMode.EDIT
        )
        change = [e for e in events if e["type"] == "change_set"][0]["change_set"]
        self.assertEqual(change["status"], "pending")
        self.assertEqual(change["summary"], "Add a count method.")
        self.assertIn("+    def count(self) -> int:", change["files"][0]["diff"])
        self.assertTrue(change["verification"]["passed"])
        self.assertEqual(
            (self.root / "todo/store.py").read_text(),
            STORE_PY,
            "nothing is written before approval",
        )
        reply = self.store.list_messages("c1")[-1]
        self.assertEqual(reply.metadata["change_set_id"], change["id"])

    def test_retry_after_non_matching_search(self) -> None:
        bad = ADD_COUNT_REPLY.replace(
            "return list(self._tasks)\n=======", "return self._tasks\n======="
        )
        router = ScriptedRouter([bad, ADD_COUNT_REPLY])
        events = self.run_turn(router, "add count", AssistantMode.EDIT)
        attempts = [e for e in events if e["type"] == "attempt"]
        self.assertEqual(attempts[0]["number"], 2)
        feedback = router.calls[1][-1]["content"]
        self.assertIn("None of your edits were applied", feedback)
        self.assertIn("closest lines", feedback)
        self.assertEqual(router.calls[1][-2]["content"], bad)
        self.assertTrue(any(e["type"] == "change_set" for e in events))

    def test_retry_after_change_that_breaks_code(self) -> None:
        breaking = ADD_COUNT_REPLY.replace(
            "return len(self._tasks)", "return self._size()"
        )
        router = ScriptedRouter([breaking, ADD_COUNT_REPLY])
        events = self.run_turn(router, "add count", AssistantMode.EDIT)
        self.assertIn(
            "would introduce",
            [e for e in events if e["type"] == "attempt"][0]["reason"],
        )
        self.assertIn("_size", router.calls[1][-1]["content"])

    def test_gives_up_after_max_attempts(self) -> None:
        bad = ADD_COUNT_REPLY.replace("def list", "def nope")
        events = self.run_turn(
            ScriptedRouter([bad, bad]),
            "add count",
            AssistantMode.EDIT,
            max_edit_attempts=2,
        )
        self.assertFalse(any(e["type"] == "change_set" for e in events))
        self.assertTrue(self.store.list_messages("c1")[-1].metadata["edit_failed"])
        self.assertIn(
            "could not produce edits",
            [e for e in events if e["type"] == "error"][0]["detail"],
        )

    def test_clarifying_question_is_not_retried(self) -> None:
        router = ScriptedRouter(["Which file do you mean?"])
        events = self.run_turn(router, "fix it", AssistantMode.EDIT)
        self.assertEqual(len(router.calls), 1)
        self.assertFalse(any(e["type"] in ("change_set", "attempt") for e in events))

    def test_whole_class_reply_is_used_as_an_edit(self) -> None:
        reply = (
            "```python\n"
            + STORE_PY.split("\n\n\n", 1)[1]
            + "\n    def count(self) -> int:\n        return len(self._tasks)\n```"
        )
        events = self.run_turn(
            ScriptedRouter([reply]), "add count to @store.py", AssistantMode.EDIT
        )
        change = [e for e in events if e["type"] == "change_set"][0]["change_set"]
        self.assertIn("+    def count(self) -> int:", change["files"][0]["diff"])

    def test_auto_fix_applies_runs_check_and_fixes(self) -> None:
        check = f"\"{sys.executable}\" -c \"import sys; sys.exit(0 if 'len(self._tasks)' in open('todo/store.py').read() else 1)\""
        conversation = Conversation("c1", "", str(self.root), check, True, 1.0, 1.0)
        first = ADD_COUNT_REPLY.replace("return len(self._tasks)", "return 0")
        second = (
            "Count the real tasks.\n\ntodo/store.py\n<<<<<<< SEARCH\n        return 0\n=======\n"
            "        return len(self._tasks)\n>>>>>>> REPLACE\n"
        )
        router = ScriptedRouter([first, second])
        events = self.run_turn(
            router, "add count", AssistantMode.EDIT, conversation=conversation
        )
        self.assertIn(
            "return len(self._tasks)", (self.root / "todo/store.py").read_text()
        )
        change_sets = self.store.list_change_sets("c1")
        self.assertEqual(
            [c.status for c in change_sets],
            [ChangeSetStatus.APPLIED, ChangeSetStatus.APPLIED],
        )
        assert change_sets[0].check is not None and change_sets[1].check is not None
        self.assertFalse(change_sets[0].check.passed)
        self.assertTrue(change_sets[1].check.passed)
        roles = [m.role for m in self.store.list_messages("c1")]
        self.assertEqual(
            roles,
            [
                MessageRole.USER,
                MessageRole.ASSISTANT,
                MessageRole.CHECK,
                MessageRole.USER,
                MessageRole.ASSISTANT,
                MessageRole.CHECK,
            ],
        )
        self.assertIn("failed with exit code 1", router.calls[1][-1]["content"])
        self.assertEqual(events[-1]["type"], "done")

    def test_auto_fix_does_not_apply_change_with_static_errors(self) -> None:
        conversation = Conversation("c1", "", str(self.root), "", True, 1.0, 1.0)
        breaking = ADD_COUNT_REPLY.replace(
            "return len(self._tasks)", "return self._size()"
        )
        self.run_turn(
            ScriptedRouter([breaking]),
            "add count",
            AssistantMode.EDIT,
            conversation=conversation,
            max_edit_attempts=1,
        )
        self.assertEqual(
            self.store.list_change_sets("c1")[0].status, ChangeSetStatus.PENDING
        )
        self.assertEqual((self.root / "todo/store.py").read_text(), STORE_PY)

    def test_helpers(self) -> None:
        self.assertEqual(
            summarize_plan(
                "todo/store.py\n<<<<<<< SEARCH", [FileChange("a.py", None, "")]
            ),
            "Edit a.py",
        )
        from forge_plugins.assistant.models import CheckResult

        text = format_check_failure(
            CheckResult("pytest", [], None, False, "x" * 5000, 1.0, timed_out=True)
        )
        self.assertIn("timed out", text)
        self.assertLess(len(text), 3500)


# ── Service ────────────────────────────────────────────────────────────────


class TestAssistantService(TempProjectCase):
    def setUp(self) -> None:
        super().setUp()
        config = MagicMock(spec=ConfigurationService)
        config.get_full_config.return_value = MagicMock(
            assistant={"context_tokens": 4096}
        )
        config.get_model_settings.return_value = ModelSettings(
            provider="ollama",
            default_model="qwen-test",
            base_url="http://x",
            temperature=0.2,
            max_tokens=100,
        )
        self.router = ScriptedRouter([ADD_COUNT_REPLY])
        registry = ServiceRegistry()
        registry.register(ConfigurationService, config)  # type: ignore[type-abstract]
        registry.register(ModelRouterService, self.router)  # type: ignore[type-abstract]
        self.service = ForgeAIAssistant(
            registry, store=SQLiteAssistantStore(":memory:")
        )
        self.service.initialize()

    def tearDown(self) -> None:
        self.service.shutdown()
        super().tearDown()

    def finish(
        self, conversation_id: str, text: str, mode: AssistantMode
    ) -> List[Dict[str, Any]]:
        return list(self.service.start_turn(conversation_id, text, mode).events())

    def test_status_uses_config(self) -> None:
        status = self.service.status()
        self.assertEqual(status["model"], "qwen-test")
        self.assertEqual(status["context_tokens"], 4096)

    def test_conversation_crud_and_validation(self) -> None:
        conversation = self.service.create_conversation(
            str(self.root), check_command="pytest -q"
        )
        self.assertEqual(Path(conversation.project_root), self.root.resolve())
        with self.assertRaises(InvalidProjectError):
            self.service.create_conversation(str(self.root / "nope"))
        with self.assertRaises(AssistantError):
            self.service.create_conversation(
                str(self.root), check_command='pytest "unclosed'
            )
        updated = self.service.update_conversation(
            conversation.id, auto_fix=True, title="T"
        )
        self.assertTrue(updated.auto_fix)
        self.assertEqual(self.service.count_conversations(), 1)
        self.assertIn("todo/store.py", self.service.list_project_files(conversation.id))
        self.assertTrue(self.service.delete_conversation(conversation.id))
        with self.assertRaises(ConversationNotFoundError):
            self.service.get_conversation(conversation.id)

    def test_turn_sets_title_and_change_lifecycle(self) -> None:
        conversation = self.service.create_conversation(str(self.root))
        events = self.finish(
            conversation.id, "Add a count method\nwith details", AssistantMode.EDIT
        )
        self.assertEqual(
            self.service.get_conversation(conversation.id).title, "Add a count method"
        )
        change_id = [e for e in events if e["type"] == "change_set"][0]["change_set"][
            "id"
        ]

        applied, check_message = self.service.apply_change_set(change_id)
        self.assertEqual(applied.status, ChangeSetStatus.APPLIED)
        self.assertIsNone(check_message)
        self.assertIn("def count", (self.root / "todo/store.py").read_text())
        with self.assertRaises(ChangeSetStateError):
            self.service.apply_change_set(change_id)
        with self.assertRaises(ChangeSetStateError):
            self.service.discard_change_set(change_id)

        reverted = self.service.revert_change_set(change_id)
        self.assertEqual(reverted.status, ChangeSetStatus.REVERTED)
        self.assertEqual((self.root / "todo/store.py").read_text(), STORE_PY)

    def test_apply_runs_check_command(self) -> None:
        conversation = self.service.create_conversation(
            str(self.root), check_command=f'"{sys.executable}" -c "print(42)"'
        )
        events = self.finish(conversation.id, "add count", AssistantMode.EDIT)
        change_id = [e for e in events if e["type"] == "change_set"][0]["change_set"][
            "id"
        ]
        applied, check_message = self.service.apply_change_set(change_id)
        assert applied.check is not None and check_message is not None
        self.assertTrue(applied.check.passed)
        self.assertEqual(check_message.role, MessageRole.CHECK)

    def test_discard(self) -> None:
        conversation = self.service.create_conversation(str(self.root))
        events = self.finish(conversation.id, "add count", AssistantMode.EDIT)
        change_id = [e for e in events if e["type"] == "change_set"][0]["change_set"][
            "id"
        ]
        self.assertEqual(
            self.service.discard_change_set(change_id).status, ChangeSetStatus.DISCARDED
        )
        self.assertEqual((self.root / "todo/store.py").read_text(), STORE_PY)

    def test_busy_conversation_rejects_second_turn(self) -> None:
        conversation = self.service.create_conversation(str(self.root))
        gate = threading.Event()
        self.router.on_chunk = gate.wait
        handle = self.service.start_turn(conversation.id, "q", AssistantMode.ASK)
        with self.assertRaises(ConversationBusyError):
            self.service.start_turn(conversation.id, "q2", AssistantMode.ASK)
        with self.assertRaises(ConversationBusyError):
            self.service.delete_conversation(conversation.id)
        self.assertTrue(self.service.stop_turn(conversation.id))
        gate.set()
        list(handle.events())
        self.assertTrue(handle.finished)
        self.assertFalse(self.service.stop_turn(conversation.id))

    def test_empty_message_rejected(self) -> None:
        conversation = self.service.create_conversation(str(self.root))
        with self.assertRaises(AssistantError):
            self.service.start_turn(conversation.id, "   ", AssistantMode.ASK)

    def test_settings_from_dict_ignores_bad_values(self) -> None:
        settings = AssistantSettings.from_dict(
            {
                "context_tokens": "big",
                "temperature": 9,
                "max_edit_attempts": 0,
                "model": 5,
            }
        )
        self.assertEqual(settings.context_tokens, 8192)
        self.assertEqual(settings.temperature, 2.0)
        self.assertEqual(settings.max_edit_attempts, 1)
        self.assertEqual(settings.model, "")


class TestStore(unittest.TestCase):
    def test_round_trip_and_cascade_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteAssistantStore(os.path.join(tmp, "a.db"))
            store.initialize()
            store.save_conversation(Conversation("c1", "t", tmp, "", False, 1.0, 2.0))
            store.add_message(message(MessageRole.USER, "hello"))
            store.save_change_set(make_change_set([FileChange("a.py", None, "x\n")]))
            self.assertEqual(store.get_change_set("cs1").files[0].original, None)  # type: ignore[union-attr]
            self.assertEqual(store.stats()["message_count"], 1)
            self.assertTrue(store.delete_conversation("c1"))
            self.assertEqual(store.list_messages("c1"), [])
            self.assertIsNone(store.get_change_set("cs1"))
            store.close()

    def test_newer_schema_is_refused(self) -> None:
        import sqlite3

        from forge_plugins.assistant.exceptions import AssistantStorageError

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.db")
            conn = sqlite3.connect(path)
            conn.execute("PRAGMA user_version = 99")
            conn.close()
            with self.assertRaises(AssistantStorageError):
                SQLiteAssistantStore(path).initialize()


if __name__ == "__main__":
    unittest.main()
