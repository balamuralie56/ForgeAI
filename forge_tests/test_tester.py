"""
Unit tests for the Tester plugin.
Verifies pipeline compilation, validation, atomic writing with merging, subprocess execution,
coverage threshold assertions, event hooks, and memory persistence.
"""

import unittest
import tempfile
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.model_router.service import ModelRouterService, ModelResponse
from forge_core.event_bus.service import EventBusService
from forge_core.memory.service import MemoryService, ForgeAIMemoryService
from forge_core.configuration.service import ConfigurationService
from forge_core.configuration.models import SystemSettings, ForgeConfig

from forge_plugins.planner.models import ProjectPlan, ProjectGoal
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport, GeneratedFile

from forge_plugins.tester.service import ForgeAITester
from forge_plugins.tester.models import GeneratedTestFile
from forge_plugins.tester.exceptions import (
    TestValidationError,
    TesterError,
    TesterWriteError,
    TestingInferenceError,
)
from forge_plugins.tester.runners.pytest_runner import PytestRunner
from forge_plugins.tester.runners.coverage_runner import CoverageRunner
from forge_plugins.tester.utils.test_pipeline import TestContext


class TestTesterPlugin(unittest.TestCase):
    """Test suite for the Tester Service."""

    def setUp(self) -> None:
        """Setup registry, temporary workspace, and service mocks."""
        self.registry = ServiceRegistry()

        # Create temporary workspace directory
        self.temp_workspace = tempfile.TemporaryDirectory()

        # 1. Setup Model Router Mock
        self.mock_router = MagicMock(spec=ModelRouterService)
        self.registry.register(ModelRouterService, self.mock_router)  # type: ignore[type-abstract]

        # 2. Setup Event Bus Mock
        self.mock_event_bus = MagicMock(spec=EventBusService)
        self.registry.register(EventBusService, self.mock_event_bus)  # type: ignore[type-abstract]

        # 3. Setup Memory Service
        self.memory = ForgeAIMemoryService(db_path=":memory:")
        self.memory.initialize()
        self.registry.register(MemoryService, self.memory)  # type: ignore[type-abstract]

        # 4. Setup Configuration Mock
        self.mock_config = MagicMock(spec=ConfigurationService)
        self.sys_settings = SystemSettings(
            workspace_dir=self.temp_workspace.name,
            log_dir="test_logs",
            log_level="INFO",
            coverage_threshold=90.0,
        )
        self.mock_config.get_system_settings.return_value = self.sys_settings
        self.mock_config.get_full_config.return_value = ForgeConfig(
            system=self.sys_settings
        )
        self.registry.register(ConfigurationService, self.mock_config)  # type: ignore[type-abstract]

        # Instantiate Tester Service
        self.tester = ForgeAITester(self.registry)

    def tearDown(self) -> None:
        """Cleanup memory engine and temporary directories."""
        self.memory.shutdown()
        self.temp_workspace.cleanup()

    def _get_mock_plan_spec_and_report(
        self,
    ) -> tuple[ProjectPlan, ArchitectureSpecification, ImplementationReport]:
        """Helper to construct inputs."""
        plan = ProjectPlan(
            goal=ProjectGoal(
                goal="Test Project", description="Description of the test goal"
            ),
            requirements=[],
            clarifications=[],
            milestones=[],
            tasks=[],
            dependencies=[],
            estimated_order=[],
            risks=[],
            assumptions=[],
        )
        spec = ArchitectureSpecification(
            project_id="test-project-123",
            directory_structure="src/\n  main.py",
            modules=[],
            database_design=[],
            decisions=[],
            adrs=[],
            mermaid_diagrams={},
            rationale="Rationale",
        )
        report = ImplementationReport(
            project_id="test-project-123",
            files=[
                GeneratedFile(
                    path="src/main.py", content="print('hello')", file_type="backend"
                )
            ],
            status="SUCCESS",
        )
        return plan, spec, report

    def test_test_project_success(self) -> None:
        """Verifies full execution pipeline success and file/event/memory outputs."""
        plan, spec, report = self._get_mock_plan_spec_and_report()

        # Write dummy file to workspace to satisfy validator checks
        workspace_dir = Path(self.temp_workspace.name)
        (workspace_dir / "src").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "src" / "main.py").write_text(
            "print('hello')", encoding="utf-8"
        )

        # Mock Pytest Runner return value directly on the tester instance
        self.tester.pytest_runner = MagicMock()
        self.tester.pytest_runner.run_tests.return_value = {
            "total": 5,
            "passed": 5,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "duration_ms": 150,
            "success": True,
            "output": "=== 5 passed in 0.15s ===",
        }

        # Mock Coverage Runner return value directly on the tester instance
        self.tester.coverage_runner = MagicMock()
        self.tester.coverage_runner.run_coverage.return_value = 92.5

        # Provide mock LLM outputs for each of the 7 generative steps in sequence
        mock_responses = [
            ModelResponse(
                text='{"files": [{"path": "tests/mock_db.py", "content": "class MockDB", "test_type": "mock"}]}',
                raw_response={},
                model_name="mock",
            ),
            ModelResponse(
                text='{"files": [{"path": "tests/conftest.py", "content": "import pytest", "test_type": "fixture"}]}',
                raw_response={},
                model_name="mock",
            ),
            ModelResponse(
                text='{"files": [{"path": "tests/test_unit.py", "content": "def test_func(): pass", "test_type": "unit"}]}',
                raw_response={},
                model_name="mock",
            ),
            ModelResponse(
                text='{"files": [{"path": "tests/test_integration.py", "content": "def test_integ(): pass", "test_type": "integration"}]}',
                raw_response={},
                model_name="mock",
            ),
            ModelResponse(
                text='{"files": [{"path": "tests/test_smoke.py", "content": "def test_smoke(): pass", "test_type": "smoke"}]}',
                raw_response={},
                model_name="mock",
            ),
            ModelResponse(
                text='{"files": [{"path": "tests/test_regression.py", "content": "def test_regr(): pass", "test_type": "regression"}]}',
                raw_response={},
                model_name="mock",
            ),
            ModelResponse(
                text='{"files": [{"path": "tests/test_coverage_plan.md", "content": "Coverage target: 90%", "test_type": "coverage"}]}',
                raw_response={},
                model_name="mock",
            ),
        ]
        self.mock_router.generate.side_effect = mock_responses

        # Run testing
        test_report = self.tester.test_project(plan, spec, report)

        # 1. Assert workspace files created
        self.assertTrue((workspace_dir / "tests" / "mock_db.py").exists())
        self.assertTrue((workspace_dir / "tests" / "conftest.py").exists())
        self.assertTrue((workspace_dir / "tests" / "test_unit.py").exists())
        self.assertTrue((workspace_dir / "tests" / "test_report.md").exists())
        self.assertTrue((workspace_dir / "test_manifest.json").exists())

        # Assert manifest contents
        manifest = json.loads(
            (workspace_dir / "test_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["total_tests"], 5)
        self.assertEqual(manifest["coverage_percentage"], 92.5)
        self.assertEqual(manifest["status"], "PASSED")

        # 2. Assert Service status and return
        self.assertEqual(test_report.status, "SUCCESS")
        self.assertTrue("Test Implementation Report" in test_report.summary)

        # 3. Assert Events published
        self.assertTrue(self.mock_event_bus.publish.called)

        # 4. Assert memory storage
        runtime_report = self.memory.runtime.get_project_state("test_report")
        self.assertIsNotNone(runtime_report)
        self.assertEqual(runtime_report["status"], "SUCCESS")

    def test_test_project_coverage_failure(self) -> None:
        """Verifies that an execution throws TesterError if coverage percentage is below threshold."""
        plan, spec, report = self._get_mock_plan_spec_and_report()

        workspace_dir = Path(self.temp_workspace.name)
        (workspace_dir / "src").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "src" / "main.py").write_text(
            "print('hello')", encoding="utf-8"
        )

        # Mock Pytest Runner return value directly on the tester instance
        self.tester.pytest_runner = MagicMock()
        self.tester.pytest_runner.run_tests.return_value = {
            "total": 5,
            "passed": 5,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "duration_ms": 150,
            "success": True,
            "output": "Success",
        }

        # Mock coverage below threshold (e.g. 85% instead of 90%)
        self.tester.coverage_runner = MagicMock()
        self.tester.coverage_runner.run_coverage.return_value = 85.0

        mock_responses = [
            ModelResponse(text='{"files": []}', raw_response={}, model_name="mock")
            for _ in range(7)
        ]
        self.mock_router.generate.side_effect = mock_responses

        # Assert TesterError raised
        with self.assertRaises(TesterError):
            self.tester.test_project(plan, spec, report)

        # Verify that coverage failed event is published
        event_types = [
            call.args[0].event_type
            for call in self.mock_event_bus.publish.call_args_list
        ]
        self.assertIn("tester.coverage_failed", event_types)

    def test_validation_failure_empty_workspace(self) -> None:
        """Verifies that validator throws error if workspace is empty."""
        plan, spec, report = self._get_mock_plan_spec_and_report()
        # Do not write files to workspace - validator should reject

        with self.assertRaises(TestValidationError):
            self.tester.test_project(plan, spec, report)

    def test_pytest_runner_stdout_parsing(self) -> None:
        """Verifies that PytestRunner correctly extracts statistics using regex patterns."""
        runner = PytestRunner()
        output = """
        ============================= test session starts =============================
        collected 5 items
        tests/test_main.py .....                                                 [100%]
        =================== 4 passed, 1 skipped in 1.45s ===================
        """
        stats = runner._parse_output(output, exit_code=0)
        self.assertEqual(stats["total"], 5)
        self.assertEqual(stats["passed"], 4)
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(stats["duration_ms"], 1450)
        self.assertTrue(stats["success"])

    def test_coverage_runner_parsing(self) -> None:
        """Verifies that CoverageRunner parses metrics successfully from json content."""
        runner = CoverageRunner()
        temp_dir = tempfile.TemporaryDirectory()

        try:
            (Path(temp_dir.name) / "tests").mkdir(parents=True, exist_ok=True)
            report_file = Path(temp_dir.name) / "coverage_report.json"
            mock_data = {"totals": {"percent_covered": 94.75}}
            report_file.write_text(json.dumps(mock_data), encoding="utf-8")

            # Monkey patch subprocess run to check backup
            with patch("subprocess.run"):
                val = runner.run_coverage(temp_dir.name)
                # Should find JSON file, read value, delete file
                self.assertEqual(val, 94.75)
                self.assertFalse(report_file.exists())
        finally:
            temp_dir.cleanup()

    def test_merge_test_files_call(self) -> None:
        """Verifies that TestWorkspaceWriter invokes model router to merge code."""
        writer = self.tester.writer
        existing = "def test_one(): assert True"
        new = "def test_two(): assert True"

        self.mock_router.generate.return_value = ModelResponse(
            text="```python\ndef test_one(): assert True\ndef test_two(): assert True\n```",
            raw_response={},
            model_name="mock",
        )

        merged = writer._merge_test_files(existing, new, self.mock_router)
        self.assertTrue("def test_one()" in merged)
        self.assertTrue("def test_two()" in merged)
        self.assertFalse("```" in merged)

    def test_pytest_runner_execution_failure(self) -> None:
        """Verifies PytestRunner handles subprocess execution errors gracefully."""
        runner = PytestRunner()
        (Path(self.temp_workspace.name) / "tests").mkdir(parents=True, exist_ok=True)
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Subprocess launch failed")
            stats = runner.run_tests(self.temp_workspace.name)
            self.assertEqual(stats["errors"], 1)
            self.assertFalse(stats["success"])

    def test_pytest_runner_timeout(self) -> None:
        """Verifies PytestRunner handles execution timeout conditions."""
        runner = PytestRunner()
        (Path(self.temp_workspace.name) / "tests").mkdir(parents=True, exist_ok=True)
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["pytest"], timeout=60)
            stats = runner.run_tests(self.temp_workspace.name)
            self.assertEqual(stats["errors"], 1)
            self.assertFalse(stats["success"])
            self.assertEqual(stats["duration_ms"], 60000)

    def test_coverage_runner_run_failure(self) -> None:
        """Verifies CoverageRunner returns 0.0 coverage on subprocess exceptions."""
        runner = CoverageRunner()
        # Create tests dir to pass check
        (Path(self.temp_workspace.name) / "tests").mkdir(parents=True, exist_ok=True)
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Coverage runner failed")
            percent = runner.run_coverage(self.temp_workspace.name)
            self.assertEqual(percent, 0.0)

    def test_test_workspace_writer_path_traversal(self) -> None:
        """Verifies that TestWorkspaceWriter blocks files escaping the workspace."""
        writer = self.tester.writer
        escaping_file = GeneratedTestFile(
            path="../../outside_test.py", content="assert True", test_type="unit"
        )
        with self.assertRaises(TesterWriteError):
            writer.write_files(self.temp_workspace.name, [escaping_file], "test-proj")

    def test_test_workspace_writer_rollback(self) -> None:
        """Verifies that TestWorkspaceWriter rolls back changes if a write exception is raised."""
        writer = self.tester.writer
        test_file = GeneratedTestFile(
            path="tests/test_fail.py", content="assert True", test_type="unit"
        )

        # Patch Path.write_text to raise an exception on write
        with patch.object(Path, "write_text", side_effect=IOError("Disk Full")):
            with self.assertRaises(TesterWriteError):
                writer.write_files(self.temp_workspace.name, [test_file], "test-proj")

            # Assert file does not exist in workspace
            workspace_dir = Path(self.temp_workspace.name)
            self.assertFalse((workspace_dir / "tests" / "test_fail.py").exists())

    def test_plugin_lifecycle(self) -> None:
        """Verifies the TesterPlugin adapter registration and shutdown routines."""
        from forge_plugins.tester.plugin import TesterPlugin

        plugin = TesterPlugin()
        self.assertEqual(plugin.name, "tester")
        self.assertEqual(plugin.version, "1.0.0")

        mock_registry = MagicMock(spec=ServiceRegistry)
        plugin.initialize(mock_registry)

        # Resolve calls
        self.assertTrue(mock_registry.register.called)

        # Shutdown
        plugin.shutdown()

    def test_validation_errors(self) -> None:
        """Verifies ImplementationValidator reports validation errors on incomplete plan, spec, or report."""
        from forge_plugins.tester.validators.implementation_validator import (
            ImplementationValidator,
        )

        validator = ImplementationValidator()
        plan, spec, report = self._get_mock_plan_spec_and_report()

        # 1. Invalid plan
        with self.assertRaises(TestValidationError):
            validator.validate(None, spec, report, self.temp_workspace.name)  # type: ignore[arg-type]

        # 2. Invalid spec
        with self.assertRaises(TestValidationError):
            validator.validate(plan, None, report, self.temp_workspace.name)  # type: ignore[arg-type]

        # 3. Invalid report
        with self.assertRaises(TestValidationError):
            validator.validate(plan, spec, None, self.temp_workspace.name)  # type: ignore[arg-type]

        # 4. Workspace does not exist
        with self.assertRaises(TestValidationError):
            validator.validate(plan, spec, report, "nonexistent_workspace_path_123")

    def test_pytest_runner_empty_tests_fallback(self) -> None:
        """Verifies PytestRunner skips execution if tests folder is missing."""
        runner = PytestRunner()
        # Pass a nonexistent workspace directory to verify skipped execution
        stats = runner.run_tests("nonexistent_workspace_path_123")
        self.assertEqual(stats["total"], 0)
        self.assertTrue(stats["success"])

    def test_pytest_runner_unmatched_stdout(self) -> None:
        """Verifies PytestRunner handles unmatched test stdout reports gracefully."""
        runner = PytestRunner()
        stats = runner._parse_output("no recognizable summary text here", exit_code=0)
        self.assertEqual(stats["total"], 0)
        self.assertTrue(stats["success"])

    def test_coverage_runner_parsing_text_fallback(self) -> None:
        """Verifies CoverageRunner falls back to standard coverage report stdout parsing when JSON is missing."""
        runner = CoverageRunner()
        (Path(self.temp_workspace.name) / "tests").mkdir(parents=True, exist_ok=True)

        # Mock subprocess run to simulate standard coverage report printing totals
        with patch("subprocess.run") as mock_run:
            mock_process = MagicMock()
            mock_process.stdout = "TOTAL      50     10    80%\n"
            mock_run.return_value = mock_process

            percent = runner.run_coverage(self.temp_workspace.name)
            self.assertEqual(percent, 80.0)

    def test_service_config_resolution_failure(self) -> None:
        """Verifies TesterService raises TesterError when system settings config throws Exception."""
        self.mock_config.get_system_settings.side_effect = Exception(
            "System Config Error"
        )
        plan, spec, report = self._get_mock_plan_spec_and_report()
        with self.assertRaises(TesterError):
            self.tester.test_project(plan, spec, report)

    def test_service_inference_error(self) -> None:
        """Verifies TesterService logs and publishes events on step inference error."""
        plan, spec, report = self._get_mock_plan_spec_and_report()
        workspace_dir = Path(self.temp_workspace.name)
        (workspace_dir / "src").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "src" / "main.py").write_text(
            "print('hello')", encoding="utf-8"
        )

        # Mock Model Router to raise error to trigger inference failure
        self.mock_router.generate.side_effect = Exception("Inference offline")

        with self.assertRaises(TesterError):
            self.tester.test_project(plan, spec, report)

    def test_service_pytest_execution_error(self) -> None:
        """Verifies TesterService raises TesterError if pytest execution reports failure."""
        plan, spec, report = self._get_mock_plan_spec_and_report()
        workspace_dir = Path(self.temp_workspace.name)
        (workspace_dir / "src").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "src" / "main.py").write_text(
            "print('hello')", encoding="utf-8"
        )

        self.tester.pytest_runner = MagicMock()
        self.tester.pytest_runner.run_tests.return_value = {
            "total": 5,
            "passed": 2,
            "failed": 3,
            "errors": 0,
            "skipped": 0,
            "success": False,
            "output": "Failed",
        }

        mock_responses = [
            ModelResponse(text='{"files": []}', raw_response={}, model_name="mock")
            for _ in range(7)
        ]
        self.mock_router.generate.side_effect = mock_responses

        with self.assertRaises(TesterError):
            self.tester.test_project(plan, spec, report)

    def test_prompt_helper_file_not_found(self) -> None:
        """Verifies load_prompt_and_generate throws TestingInferenceError on missing templates."""
        from forge_plugins.tester.utils.prompt_helper import load_prompt_and_generate

        plan, spec, report = self._get_mock_plan_spec_and_report()
        context = TestContext(
            project_plan=plan,
            architecture=spec,
            implementation_report=report,
            workspace=self.temp_workspace.name,
            model_router=self.mock_router,
            event_bus=self.mock_event_bus,
            configuration=self.mock_config.get_full_config(),
            memory=self.memory,
            logger=MagicMock(),
        )

        with self.assertRaises(TestingInferenceError):
            load_prompt_and_generate(
                context, "non_existent_prompt_template_file", "unit"
            )

    def test_prompt_helper_json_decode_failure(self) -> None:
        """Verifies load_prompt_and_generate throws TestingInferenceError on malformed JSON response."""
        from forge_plugins.tester.utils.prompt_helper import load_prompt_and_generate

        plan, spec, report = self._get_mock_plan_spec_and_report()
        context = TestContext(
            project_plan=plan,
            architecture=spec,
            implementation_report=report,
            workspace=self.temp_workspace.name,
            model_router=self.mock_router,
            event_bus=self.mock_event_bus,
            configuration=self.mock_config.get_full_config(),
            memory=self.memory,
            logger=MagicMock(),
        )

        # Mock invalid JSON response format
        self.mock_router.generate.return_value = ModelResponse(
            text="Invalid JSON non-structured payload string",
            raw_response={},
            model_name="mock",
        )

        with self.assertRaises(TestingInferenceError):
            load_prompt_and_generate(context, "unit", "unit")

    def test_workspace_writer_merge_exception_fallback(self) -> None:
        """Verifies TestWorkspaceWriter falls back to direct override if merge generation raises error."""
        writer = self.tester.writer
        existing = "def test_one(): assert True"
        new = "def test_two(): assert True"

        # Mock ModelRouter to raise an error during merge
        self.mock_router.generate.side_effect = Exception("Model service busy")

        # Should fallback to returning the new code content without crash
        merged = writer._merge_test_files(existing, new, self.mock_router)
        self.assertEqual(merged, new)

    def test_workspace_writer_rollback_restores_backup(self) -> None:
        """Verifies TestWorkspaceWriter restores original files from backup if write error occurs mid-run."""
        writer = self.tester.writer
        workspace_dir = Path(self.temp_workspace.name)
        (workspace_dir / "tests").mkdir(parents=True, exist_ok=True)

        # Pre-populate an existing file
        existing_file = workspace_dir / "tests" / "test_existing.py"
        existing_file.write_text("# Original content", encoding="utf-8")

        # Define file writes where the second file write fails
        files = [
            GeneratedTestFile(
                path="tests/test_existing.py",
                content="# Updated content",
                test_type="unit",
            ),
            GeneratedTestFile(
                path="tests/test_fail.py", content="content", test_type="unit"
            ),
        ]

        # Patch Path.write_text to raise an exception ONLY when writing the second file
        original_write_text = Path.write_text

        def side_effect_write(self_path, *args, **kwargs):
            if "test_fail.py" in str(self_path):
                raise IOError("Write failed")
            return original_write_text(self_path, *args, **kwargs)

        with patch.object(Path, "write_text", side_effect=side_effect_write):
            with self.assertRaises(TesterWriteError):
                writer.write_files(
                    self.temp_workspace.name,
                    files,
                    "test-proj",
                    model_router=self.mock_router,
                )

            # Assert existing file is restored back to its original backup contents
            self.assertEqual(
                existing_file.read_text(encoding="utf-8"), "# Original content"
            )
            # Assert failing file does not exist
            self.assertFalse((workspace_dir / "tests" / "test_fail.py").exists())

    def test_pytest_runner_no_tests_collected(self) -> None:
        """Verifies PytestRunner parses collected 0 items as success."""
        runner = PytestRunner()
        stats = runner._parse_output("collected 0 items", exit_code=0)
        self.assertEqual(stats["total"], 0)
        self.assertTrue(stats["success"])

    def test_pytest_runner_successful_execution(self) -> None:
        """Verifies PytestRunner successfully executes pytest subprocess and returns success state."""
        runner = PytestRunner()
        (Path(self.temp_workspace.name) / "tests").mkdir(parents=True, exist_ok=True)
        with patch("subprocess.run") as mock_run:
            mock_process = MagicMock()
            mock_process.stdout = "=== 5 passed in 0.15s ==="
            mock_process.stderr = ""
            mock_process.return_code = 0
            mock_run.return_value = mock_process
            stats = runner.run_tests(self.temp_workspace.name)
            self.assertEqual(stats["total"], 5)
            self.assertEqual(stats["passed"], 5)

    def test_service_unexpected_step_failure(self) -> None:
        """Verifies TesterService raises TesterError when pipeline step throws unexpected Exception."""
        plan, spec, report = self._get_mock_plan_spec_and_report()
        workspace_dir = Path(self.temp_workspace.name)
        (workspace_dir / "src").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "src" / "main.py").write_text(
            "print('hello')", encoding="utf-8"
        )

        # Mock ModelRouter to raise arbitrary exception during step execution
        self.mock_router.generate.side_effect = ValueError("Corrupt config text")
        with self.assertRaises(TesterError):
            self.tester.test_project(plan, spec, report)

    def test_service_write_generic_exception(self) -> None:
        """Verifies TesterService maps generic workspace writing exception to TesterError."""
        plan, spec, report = self._get_mock_plan_spec_and_report()
        workspace_dir = Path(self.temp_workspace.name)
        (workspace_dir / "src").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "src" / "main.py").write_text(
            "print('hello')", encoding="utf-8"
        )

        mock_responses = [
            ModelResponse(text='{"files": []}', raw_response={}, model_name="mock")
            for _ in range(7)
        ]
        self.mock_router.generate.side_effect = mock_responses

        # Patch write_files to raise generic exception
        with patch.object(
            self.tester.writer, "write_files", side_effect=RuntimeError("Disk crash")
        ):
            with self.assertRaises(TesterError):
                self.tester.test_project(plan, spec, report)

    def test_service_memory_storage_exception(self) -> None:
        """Verifies TesterService continues successfully even if memory persistence raises Exception."""
        plan, spec, report = self._get_mock_plan_spec_and_report()
        workspace_dir = Path(self.temp_workspace.name)
        (workspace_dir / "src").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "src" / "main.py").write_text(
            "print('hello')", encoding="utf-8"
        )

        # Mock Pytest and Coverage success
        self.tester.pytest_runner = MagicMock()
        self.tester.pytest_runner.run_tests.return_value = {
            "total": 5,
            "passed": 5,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "success": True,
            "output": "Pass",
        }
        self.tester.coverage_runner = MagicMock()
        self.tester.coverage_runner.run_coverage.return_value = 95.0

        mock_responses = [
            ModelResponse(text='{"files": []}', raw_response={}, model_name="mock")
            for _ in range(7)
        ]
        self.mock_router.generate.side_effect = mock_responses

        # Mock memory to raise exception
        with patch.object(
            self.memory.runtime,
            "set_project_state",
            side_effect=Exception("Database locked"),
        ):
            # Should complete successfully because it catches memory write exceptions internally
            test_report = self.tester.test_project(plan, spec, report)
            self.assertEqual(test_report.status, "SUCCESS")

    def test_workspace_writer_existing_file_read_failure(self) -> None:
        """Verifies TestWorkspaceWriter handles existing file read errors safely during writes."""
        writer = self.tester.writer
        workspace_dir = Path(self.temp_workspace.name)
        (workspace_dir / "tests").mkdir(parents=True, exist_ok=True)
        existing_file = workspace_dir / "tests" / "test_unreadable.py"
        existing_file.write_text("# content", encoding="utf-8")

        files = [
            GeneratedTestFile(
                path="tests/test_unreadable.py",
                content="# new content",
                test_type="unit",
            )
        ]

        # Patch Path.read_text to raise an exception, verifying backup state continues safely
        with patch.object(Path, "read_text", side_effect=IOError("Permission denied")):
            writer.write_files(
                self.temp_workspace.name,
                files,
                "test-proj",
                model_router=self.mock_router,
            )
        # Content should still be overwritten successfully
        self.assertEqual(existing_file.read_text(encoding="utf-8"), "# new content")

    def test_workspace_writer_rollback_exception_handling(self) -> None:
        """Verifies TestWorkspaceWriter logs but does not crash if a rollback deletes a file that throws Exception."""
        writer = self.tester.writer
        workspace_dir = Path(self.temp_workspace.name)
        (workspace_dir / "tests").mkdir(parents=True, exist_ok=True)

        # We write a file successfully, but make subsequent rollback throw an exception on unlink

        # Patch Path.write_text to trigger rollback, and patch Path.unlink to throw exception
        with patch.object(Path, "write_text", side_effect=[None, IOError("Disk Full")]):
            with patch.object(Path, "unlink", side_effect=IOError("File locked")):
                with self.assertRaises(TesterWriteError):
                    # We pass two files (first succeeds, second triggers rollback where unlink fails)
                    writer.write_files(
                        self.temp_workspace.name,
                        [
                            GeneratedTestFile(
                                path="tests/test_rollback_err.py",
                                content="# 1",
                                test_type="unit",
                            ),
                            GeneratedTestFile(
                                path="tests/test_rollback_err2.py",
                                content="# 2",
                                test_type="unit",
                            ),
                        ],
                        "test-proj",
                    )
