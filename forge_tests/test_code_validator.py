"""
Tests for the Developer Plugin's static code validator and its pipeline wiring.
"""

import tempfile
import unittest
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock

from forge_core.configuration.models import ForgeConfig, SystemSettings
from forge_core.configuration.service import ConfigurationService
from forge_core.event_bus.service import EventBusService
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.memory.service import ForgeAIMemoryService, MemoryService
from forge_core.model_router.service import ModelResponse, ModelRouterService
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import (
    CodeValidationResult,
    GeneratedFile,
    ImplementationReport,
    ImplementationStatus,
    IssueSeverity,
    ValidationIssue,
)
from forge_plugins.developer.service import ForgeAIDeveloper
from forge_plugins.developer.validators.code_validator import GeneratedCodeValidator
from forge_plugins.planner.models import ProjectGoal, ProjectPlan


def validate(files: Dict[str, str]) -> CodeValidationResult:
    return GeneratedCodeValidator().validate(
        [GeneratedFile(path=p, content=c, file_type="code") for p, c in files.items()]
    )


def checks(result: CodeValidationResult) -> List[str]:
    return [i.check for i in result.issues]


class TestSyntaxAndFormats(unittest.TestCase):
    def test_valid_project_passes_cleanly(self) -> None:
        result = validate(
            {
                "app/__init__.py": "",
                "app/models.py": "from dataclasses import dataclass\n\n@dataclass\nclass Task:\n    title: str\n",
                "app/main.py": "from app.models import Task\n\ndef make() -> Task:\n    return Task('x')\n",
                "config.json": '{"debug": false}',
                "pyproject.toml": '[project]\nname = "demo"\ndependencies = []\n',
            }
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.issues, [])
        self.assertEqual(result.checked_files, 5)
        self.assertEqual(result.status, ImplementationStatus.SUCCESS)

    def test_python_syntax_error_is_reported_with_line(self) -> None:
        result = validate({"api.py": "x = 1\nclass Route\n"})
        self.assertFalse(result.passed)
        self.assertEqual(result.errors[0].check, "syntax")
        self.assertEqual(result.errors[0].line, 2)

    def test_null_bytes_are_a_syntax_error_not_a_crash(self) -> None:
        result = validate({"bad.py": "x = 1\x00"})
        self.assertEqual(checks(result), ["syntax"])

    def test_invalid_json_is_an_error(self) -> None:
        result = validate({"config.json": '{"a": 1,}'})
        self.assertEqual(checks(result), ["json"])
        self.assertEqual(result.errors[0].line, 1)

    def test_invalid_toml_is_an_error(self) -> None:
        result = validate({"pyproject.toml": "[project\nname = 'x'"})
        self.assertEqual(checks(result), ["toml"])

    def test_non_code_files_are_not_checked(self) -> None:
        result = validate(
            {"index.html": "<h1>", "styles.css": "a {", "README.md": "# x"}
        )
        self.assertEqual(result.checked_files, 0)
        self.assertTrue(result.passed)

    def test_empty_input(self) -> None:
        result = validate({})
        self.assertEqual(result.checked_files, 0)
        self.assertEqual(result.status, ImplementationStatus.SUCCESS)


class TestImports(unittest.TestCase):
    def test_relative_import_in_top_level_module_is_an_error(self) -> None:
        result = validate(
            {"main.py": "from .tasks import add\n", "tasks.py": "def add(): return 1\n"}
        )
        self.assertEqual(checks(result), ["import"])
        self.assertIn("no known parent package", result.errors[0].message)

    def test_relative_import_inside_package_resolves(self) -> None:
        result = validate(
            {
                "pkg/__init__.py": "",
                "pkg/models.py": "class Task:\n    title = ''\n",
                "pkg/service.py": "from .models import Task\nfrom . import models\n\nT = (Task, models)\n",
            }
        )
        self.assertEqual(result.issues, [])

    def test_relative_import_of_missing_module_is_an_error(self) -> None:
        result = validate(
            {"pkg/__init__.py": "", "pkg/a.py": "from .adrs import ADR_001\n"}
        )
        self.assertEqual(checks(result), ["import"])

    def test_relative_import_climbing_above_top_package_is_an_error(self) -> None:
        result = validate({"pkg/a.py": "from ..other import x\n"})
        self.assertIn("above the top-level package", result.errors[0].message)

    def test_parent_relative_import_resolves(self) -> None:
        result = validate(
            {
                "pkg/__init__.py": "",
                "pkg/util.py": "def helper(): return 1\n",
                "pkg/sub/__init__.py": "",
                "pkg/sub/mod.py": "from ..util import helper\n\nX = helper()\n",
            }
        )
        self.assertEqual(result.issues, [])

    def test_sibling_script_import_resolves(self) -> None:
        # python todo/main.py puts todo/ on sys.path, so "import tasks" works.
        result = validate(
            {
                "todo/main.py": "from tasks import add_task\n\nadd_task()\n",
                "todo/tasks.py": "def add_task():\n    return 1\n",
            }
        )
        self.assertEqual(result.issues, [])

    def test_ambiguous_import_is_only_an_error_if_every_candidate_lacks_the_name(
        self,
    ) -> None:
        # "from tasks import ..." in pkg/main.py means pkg/tasks.py when run as a
        # script but tasks.py when run with -m from the root; either is valid.
        files = {
            "tasks.py": "def add():\n    return 1\n",
            "pkg/tasks.py": "def remove():\n    return 2\n",
        }
        ok = validate({**files, "pkg/main.py": "from tasks import add, remove\n"})
        self.assertEqual(ok.errors, [])

        broken = validate({**files, "pkg/main.py": "from tasks import missing\n"})
        self.assertEqual(checks(broken), ["import"])
        self.assertIn("pkg/tasks.py", broken.errors[0].message)
        self.assertIn(", tasks.py", broken.errors[0].message)

    def test_src_layout_import_resolves(self) -> None:
        result = validate(
            {
                "src/app/__init__.py": "",
                "src/app/core.py": "VALUE = 1\n",
                "tests/test_core.py": "from app.core import VALUE\n\nassert VALUE\n",
            }
        )
        self.assertEqual(result.issues, [])

    def test_missing_submodule_of_local_package_is_an_error(self) -> None:
        result = validate({"app/__init__.py": "", "main.py": "import app.missing\n"})
        self.assertEqual(checks(result), ["import"])
        self.assertIn("app.missing", result.errors[0].message)

    def test_importing_undefined_name_from_local_module_is_an_error(self) -> None:
        result = validate(
            {
                "models.py": "class TaskModel:\n    id = 0\n",
                "main.py": "from models import Task\n",
            }
        )
        self.assertEqual(checks(result), ["import"])
        self.assertIn("'Task'", result.errors[0].message)

    def test_names_bound_conditionally_or_by_import_count_as_defined(self) -> None:
        result = validate(
            {
                "compat.py": "import sys\nif sys.version_info >= (3, 11):\n    import tomllib as toml\nelse:\n    toml = None\nfrom os import path as p\nfor INDEX in range(1):\n    pass\n",
                "main.py": "from compat import toml, p, INDEX, sys\n",
            }
        )
        self.assertEqual(result.errors, [])

    def test_star_import_or_module_getattr_disables_name_check(self) -> None:
        result = validate(
            {
                "dyn.py": "def __getattr__(name):\n    return name\n",
                "star.py": "from os.path import *\n",
                "main.py": "from dyn import anything\nfrom star import whatever\n",
            }
        )
        self.assertEqual(result.errors, [])

    def test_package_submodule_can_be_imported_by_name(self) -> None:
        result = validate(
            {
                "pkg/__init__.py": "",
                "pkg/routes.py": "R = 1\n",
                "main.py": "from pkg import routes\n",
            }
        )
        self.assertEqual(result.issues, [])

    def test_namespace_package_submodule_resolves(self) -> None:
        result = validate(
            {
                "ns/mod.py": "X = 1\n",
                "main.py": "from ns import mod\nfrom ns.mod import X\n",
            }
        )
        self.assertEqual(result.issues, [])

    def test_guarded_optional_import_is_not_flagged(self) -> None:
        result = validate(
            {
                "main.py": "try:\n    import ujson as json\nexcept ImportError:\n    import json\n",
                "requirements.txt": "",
            }
        )
        self.assertEqual(result.issues, [])

    def test_stdlib_imports_are_never_flagged(self) -> None:
        result = validate(
            {
                "main.py": "from __future__ import annotations\nimport json, os.path\nfrom collections import OrderedDict\n"
            }
        )
        self.assertEqual(result.issues, [])

    def test_windows_and_dot_prefixed_paths_are_normalized(self) -> None:
        result = validate(
            {
                "pkg\\__init__.py": "",
                "./pkg/a.py": "X = 1\n",
                "pkg\\b.py": "from .a import X\n",
            }
        )
        self.assertEqual(result.issues, [])


class TestDependencies(unittest.TestCase):
    def test_declared_dependencies_pass(self) -> None:
        result = validate(
            {
                "requirements.txt": "# deps\nFastAPI>=0.100  # web\nuvicorn[standard]==0.30\npydantic_settings\nPyYAML\n-r extra.txt\n",
                "main.py": "import fastapi, uvicorn, yaml\nfrom pydantic_settings import BaseSettings\n",
            }
        )
        self.assertEqual(result.issues, [])

    def test_undeclared_dependency_is_a_warning(self) -> None:
        result = validate(
            {
                "requirements.txt": "fastapi\n",
                "main.py": "import fastapi\nimport pydantic\n",
            }
        )
        self.assertTrue(result.passed)
        self.assertEqual(checks(result), ["dependency"])
        self.assertEqual(result.status, ImplementationStatus.SUCCESS_WITH_WARNINGS)

    def test_missing_manifest_is_reported_once_per_package(self) -> None:
        result = validate(
            {"a.py": "import requests\n", "b.py": "import requests\nX = 1\n"}
        )
        self.assertEqual(checks(result), ["dependency"])
        self.assertIn("no requirements.txt", result.warnings[0].message)

    def test_pyproject_and_poetry_dependencies_are_recognized(self) -> None:
        result = validate(
            {
                "pyproject.toml": '[project]\ndependencies = ["httpx>=0.27"]\n[tool.poetry.dependencies]\npython = "^3.13"\nrich = "*"\n',
                "main.py": "import httpx\nimport rich\n",
            }
        )
        self.assertEqual(result.issues, [])


class TestNamesAndLeftovers(unittest.TestCase):
    def test_undefined_name_is_an_error_at_first_use(self) -> None:
        result = validate(
            {
                "tasks.py": "import json\n\ndef add() -> JSONResponse:\n    return JSONResponse()\n"
            }
        )
        self.assertEqual(checks(result), ["undefined-name"])
        self.assertEqual(result.errors[0].line, 3)

    def test_every_binding_form_counts_as_defined(self) -> None:
        source = (
            "import os.path\n"
            "from typing import List as L\n"
            "G = 1\n"
            "def f(a, /, b, *args, c, **kw):\n"
            "    global H\n"
            "    H = [x for x in args]\n"
            "    with open(__file__) as fh:\n"
            "        pass\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as err:\n"
            "        print(err)\n"
            "    if (n := len(kw)) > 0:\n"
            "        return n\n"
            "    match a:\n"
            "        case {'k': v, **rest}:\n"
            "            return v, rest\n"
            "        case [first, *others]:\n"
            "            return first, others\n"
            "        case other:\n"
            "            return other\n"
            "    return lambda q: q + b + c + G + H + fh.closed\n"
            "class K:\n"
            "    def m(self) -> 'K':\n"
            "        return __class__\n"
            "def g[T](x: T) -> T:\n"
            "    return x\n"
            "X: L[int] = [os.path.sep and 1]\n"
        )
        result = validate({"forms.py": source})
        self.assertEqual(result.issues, [], [i.message for i in result.issues])

    def test_star_import_disables_undefined_name_check(self) -> None:
        result = validate({"m.py": "from os.path import *\nprint(join('a', 'b'))\n"})
        self.assertEqual(result.issues, [])

    def test_placeholder_comments_and_stubs_are_warnings(self) -> None:
        result = validate(
            {
                "m.py": (
                    "# TODO: write this\n"
                    "def a():\n    pass\n"
                    "def b():\n    '''Doc.'''\n    ...\n"
                    "def c():\n    raise NotImplementedError('later')\n"
                    "def d():\n    return 1  # dummy implementation\n"
                )
            }
        )
        self.assertTrue(result.passed)
        self.assertEqual(checks(result), ["placeholder"] * 5)

    def test_abstract_overload_and_protocol_stubs_are_not_flagged(self) -> None:
        result = validate(
            {
                "m.py": (
                    "from abc import ABC, abstractmethod\n"
                    "from typing import Protocol, overload\n"
                    "class Base(ABC):\n    @abstractmethod\n    def run(self) -> None:\n        ...\n"
                    "class Port(Protocol):\n    def send(self) -> None: ...\n"
                    "@overload\ndef f(x: int) -> int: ...\n"
                    "@overload\ndef f(x: str) -> str: ...\n"
                    "def f(x):\n    return x\n"
                )
            }
        )
        self.assertEqual(result.issues, [])

    def test_exception_class_with_pass_body_is_not_flagged(self) -> None:
        result = validate({"errors.py": "class AppError(Exception):\n    pass\n"})
        self.assertEqual(result.issues, [])

    def test_identical_modules_are_flagged_as_duplicates(self) -> None:
        body = "def run():\n    return 1\n"
        result = validate(
            {
                "a.py": body,
                "b.py": body + "\n",
                "pkg/__init__.py": "",
                "x/__init__.py": "",
            }
        )
        self.assertEqual(checks(result), ["duplicate"])
        self.assertIn("a.py", result.warnings[0].message)

    def test_same_path_generated_twice_validates_the_last_version(self) -> None:
        result = GeneratedCodeValidator().validate(
            [
                GeneratedFile(path="main.py", content="broken(", file_type="api"),
                GeneratedFile(path="main.py", content="X = 1\n", file_type="backend"),
            ]
        )
        self.assertTrue(result.passed)
        self.assertEqual(checks(result), ["duplicate"])

    def test_errors_are_sorted_before_warnings(self) -> None:
        result = validate({"a.py": "# TODO\n", "z.py": "x = (\n"})
        self.assertEqual(
            [i.severity for i in result.issues],
            [IssueSeverity.ERROR, IssueSeverity.WARNING],
        )


class TestRegressionRealModelOutput(unittest.TestCase):
    """
    Files qwen2.5-coder:3b actually generated for "a command-line todo list
    manager" (2026-11-17). The run was reported as SUCCESS; these defects made
    the root package unimportable.
    """

    ROOT_MAIN = (
        "import json\n"
        "from fastapi import FastAPI\n"
        "from fastapi.responses import JSONResponse\n"
        "from .tasks import add_task, remove_task, list_tasks\n"
        "\n"
        "app = FastAPI()\n"
        "\n"
        "@app.post('/api/v1/tasks', response_model=JSONResponse)\n"
        "def add_task(task: str):\n"
        "    return add_task(task)\n"
    )
    ROOT_TASKS = (
        "import json\n"
        "from typing import List\n"
        "from .models import Task\n"
        "from .adrs import ADR_001\n"
        "\n"
        "DB_PATH = 'tasks.db'\n"
        "\n"
        "if not ADR_001.is_accepted:\n"
        "    raise Exception('ADR-001 is not accepted. Please implement SQLite database access.')\n"
        "\n"
        "# Dummy implementation to show how task handling might be done\n"
        "\n"
        "def add_task(task: str) -> JSONResponse:\n"
        "    with open(DB_PATH, 'r') as f:\n"
        "        tasks = json.load(f)\n"
        "    tasks.append(Task(task=task))\n"
        "    return JSONResponse(content={'message': 'Task added successfully'})\n"
        "\n"
        "# Dummy task model\n"
        "\n"
        "class Task:\n"
        "    def __init__(self, task: str):\n"
        "        self.id = 1\n"
        "        self.task = task\n"
    )
    PKG_MAIN = (
        "from fastapi import FastAPI\n"
        "from tasks import add_task, remove_task, list_tasks\n"
        "from models import TaskModel\n"
        "from pydantic import BaseModel\n"
        "import json\n"
        "\n"
        "app = FastAPI()\n"
        "\n"
        "class Task(BaseModel):\n"
        "    task: str\n"
    )
    PKG_TASKS = (
        "from fastapi import FastAPI\n"
        "from models import TaskModel\n"
        "import json\n"
        "\n"
        "def add_task(task):\n"
        "    return task\n"
        "\n"
        "def remove_task(task_id: int):\n"
        "    return task_id\n"
        "\n"
        "def list_tasks(sort: str = None):\n"
        "    return [TaskModel(id=1, task='x')]\n"
    )

    def test_real_broken_output_fails_validation_with_the_real_defects(self) -> None:
        result = validate(
            {
                "requirements.txt": "fastapi>=0.100.0\nuvicorn>=0.22.0\nsqlalchemy>=2.0.0\npydantic-settings>=2.0.0\n",
                "src/config.py": "from pydantic_settings import BaseSettings\n\nclass Settings(BaseSettings):\n    PORT: int = 8000\n",
                "main.py": self.ROOT_MAIN,
                "tasks.py": self.ROOT_TASKS,
                "todo_list_manager/main.py": self.PKG_MAIN,
                "todo_list_manager/tasks.py": self.PKG_TASKS,
                "todo_list_manager/models.py": "from pydantic import BaseModel\n\nclass TaskModel(BaseModel):\n    id: int\n    task: str\n",
                "schema.sql": "CREATE TABLE tasks (id INTEGER PRIMARY KEY);",
            }
        )

        self.assertEqual(result.status, ImplementationStatus.VALIDATION_FAILED)
        found = {(i.path, i.check, i.line) for i in result.errors}
        self.assertIn(("main.py", "import", 4), found)
        self.assertIn(("tasks.py", "import", 3), found)
        self.assertIn(("tasks.py", "import", 4), found)
        self.assertIn(("tasks.py", "undefined-name", 13), found)
        self.assertEqual(len(result.errors), 4)
        self.assertIn(
            ("todo_list_manager/main.py", "dependency"),
            {(i.path, i.check) for i in result.warnings},
        )
        self.assertFalse(
            any(i.path.startswith("todo_list_manager") for i in result.errors)
        )


class TestModels(unittest.TestCase):
    def test_result_round_trips_through_dict(self) -> None:
        original = validate({"a.py": "x = (\n", "b.py": "# TODO\n"})
        restored = CodeValidationResult.from_dict(original.to_dict())
        self.assertEqual(restored, original)
        data = original.to_dict()
        self.assertEqual(
            (data["passed"], data["error_count"], data["warning_count"]), (False, 1, 1)
        )

    def test_report_from_before_validation_existed_still_loads(self) -> None:
        report = ImplementationReport.from_dict(
            {"project_id": "p", "files": [], "summary": "", "status": "SUCCESS"}
        )
        self.assertIsNone(report.validation)
        self.assertIsNone(report.to_dict()["validation"])

    def test_report_round_trips_validation(self) -> None:
        validation = CodeValidationResult(
            checked_files=1,
            issues=[ValidationIssue(IssueSeverity.ERROR, "syntax", "a.py", "bad", 3)],
        )
        report = ImplementationReport(
            project_id="p", status=validation.status.value, validation=validation
        )
        self.assertEqual(ImplementationReport.from_dict(report.to_dict()), report)


def _response(path: str, content: str, file_type: str) -> ModelResponse:
    import json

    return ModelResponse(
        text=json.dumps(
            {"files": [{"path": path, "content": content, "file_type": file_type}]}
        ),
        raw_response={},
        model_name="mock-model",
    )


class TestDeveloperReportsValidation(unittest.TestCase):
    """The Developer service runs validation and reports an honest status."""

    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        registry = ServiceRegistry()
        self.router = MagicMock(spec=ModelRouterService)
        registry.register(ModelRouterService, self.router)  # type: ignore[type-abstract]
        self.event_bus = MagicMock(spec=EventBusService)
        registry.register(EventBusService, self.event_bus)  # type: ignore[type-abstract]
        self.memory = ForgeAIMemoryService(db_path=":memory:")
        self.memory.initialize()
        registry.register(MemoryService, self.memory)  # type: ignore[type-abstract]
        config = MagicMock(spec=ConfigurationService)
        settings = SystemSettings(
            workspace_dir=self.workspace.name, log_dir="test_logs", log_level="INFO"
        )
        config.get_system_settings.return_value = settings
        config.get_full_config.return_value = ForgeConfig(system=settings)
        registry.register(ConfigurationService, config)  # type: ignore[type-abstract]
        self.developer = ForgeAIDeveloper(registry)
        self.plan = ProjectPlan(goal=ProjectGoal(goal="Todo", description="d"))
        self.spec = ArchitectureSpecification(
            project_id="todo", directory_structure="main.py", rationale="r"
        )

    def tearDown(self) -> None:
        self.memory.shutdown()
        self.workspace.cleanup()

    def _run(self, api_content: str, backend_content: str) -> ImplementationReport:
        self.router.generate.side_effect = [
            _response("requirements.txt", "fastapi\n", "dependency"),
            _response(".env", "PORT=8000", "environment"),
            _response("config.json", "{}", "configuration"),
            _response("schema.sql", "CREATE TABLE t (id INTEGER);", "database"),
            _response("api.py", api_content, "api"),
            _response("main.py", backend_content, "backend"),
            _response("index.html", "<h1>x</h1>", "frontend"),
        ]
        return self.developer.implement_project(self.plan, self.spec)

    def test_valid_code_is_reported_as_success(self) -> None:
        report = self._run(
            "import fastapi\nAPP = fastapi.FastAPI()\n", "from api import APP\n"
        )
        self.assertEqual(report.status, "SUCCESS")
        assert report.validation is not None
        self.assertTrue(report.validation.passed)

    def test_broken_code_is_reported_as_validation_failed_but_still_written(
        self,
    ) -> None:
        report = self._run(
            "from .missing import x\n", "def run() -> Response:\n    return 1\n"
        )

        self.assertEqual(report.status, "VALIDATION_FAILED")
        assert report.validation is not None
        self.assertEqual(
            sorted(i.check for i in report.validation.errors),
            ["import", "undefined-name"],
        )
        workspace = Path(self.workspace.name)
        self.assertTrue((workspace / "api.py").exists())
        markdown = (workspace / "implementation_report.md").read_text(encoding="utf-8")
        self.assertIn("## Code Validation", markdown)
        self.assertIn("VALIDATION_FAILED", markdown)
        self.assertIn("`main.py:1`", markdown)

        stored = self.memory.project.get_metadata("implementation_report")
        self.assertEqual(stored["status"], "VALIDATION_FAILED")
        self.assertEqual(stored["validation"]["error_count"], 2)

        published = {
            c[0][0].event_type: c[0][0].data
            for c in self.event_bus.publish.call_args_list
        }
        self.assertEqual(
            published["developer.validated"]["status"], "VALIDATION_FAILED"
        )
        self.assertEqual(
            published["developer.completed"]["status"], "VALIDATION_FAILED"
        )

    def test_warnings_only_is_reported_as_success_with_warnings(self) -> None:
        report = self._run(
            "import pydantic\nX = pydantic\n", "# TODO: wire up\nY = 1\n"
        )
        self.assertEqual(report.status, "SUCCESS_WITH_WARNINGS")

    def test_markdown_escapes_pipes_in_messages(self) -> None:
        self._run("X = 1\n", "x = (1 |\n")
        markdown = (Path(self.workspace.name) / "implementation_report.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("| | ", markdown.split("## Code Validation")[1])


if __name__ == "__main__":
    unittest.main()
