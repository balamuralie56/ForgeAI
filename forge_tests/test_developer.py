"""
Unit tests for the Developer plugin.
Verifies compilation pipeline, validation, atomic writing with rollback, event hooks, and memory persistence.
"""

import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.model_router.service import ModelRouterService, ModelResponse
from forge_core.event_bus.service import EventBusService
from forge_core.memory.service import MemoryService, ForgeAIMemoryService
from forge_core.configuration.service import ConfigurationService
from forge_core.configuration.models import SystemSettings, ForgeConfig

from forge_plugins.planner.models import ProjectPlan, ProjectGoal
from forge_plugins.architect.models import ArchitectureSpecification

from forge_plugins.developer.service import ForgeAIDeveloper
from forge_plugins.developer.exceptions import (
    DeveloperValidationError,
    DeveloperError,
)


class TestDeveloperPlugin(unittest.TestCase):
    """Test suite for the Developer Service."""

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
        )
        self.mock_config.get_system_settings.return_value = self.sys_settings
        self.mock_config.get_full_config.return_value = ForgeConfig(
            system=self.sys_settings
        )
        self.registry.register(ConfigurationService, self.mock_config)  # type: ignore[type-abstract]

        self.developer = ForgeAIDeveloper(self.registry)

    def tearDown(self) -> None:
        """Cleanup memory engine and temporary directories."""
        self.memory.shutdown()
        self.temp_workspace.cleanup()

    def _get_mock_plan_and_spec(self) -> tuple[ProjectPlan, ArchitectureSpecification]:
        """Helper to construct basic inputs."""
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
        return plan, spec

    def test_implement_project_success(self) -> None:
        """Verifies full execution pipeline success and file/event/memory outputs."""
        plan, spec = self._get_mock_plan_and_spec()

        # Provide mock LLM outputs for each of the 7 generative steps in sequence
        mock_responses = [
            ModelResponse(
                text='{"files": [{"path": "requirements.txt", "content": "fastapi>=0.100.0", "file_type": "dependency"}]}',
                raw_response={},
                model_name="mock-model",
            ),
            ModelResponse(
                text='{"files": [{"path": ".env", "content": "PORT=8000", "file_type": "environment"}]}',
                raw_response={},
                model_name="mock-model",
            ),
            ModelResponse(
                text='{"files": [{"path": "config.json", "content": "{}", "file_type": "configuration"}]}',
                raw_response={},
                model_name="mock-model",
            ),
            ModelResponse(
                text='{"files": [{"path": "schema.sql", "content": "CREATE TABLE users", "file_type": "database"}]}',
                raw_response={},
                model_name="mock-model",
            ),
            ModelResponse(
                text='{"files": [{"path": "api.py", "content": "class Route", "file_type": "api"}]}',
                raw_response={},
                model_name="mock-model",
            ),
            ModelResponse(
                text='{"files": [{"path": "main.py", "content": "import sys", "file_type": "backend"}]}',
                raw_response={},
                model_name="mock-model",
            ),
            ModelResponse(
                text='{"files": [{"path": "index.html", "content": "<h1>Forge</h1>", "file_type": "frontend"}]}',
                raw_response={},
                model_name="mock-model",
            ),
        ]
        self.mock_router.generate.side_effect = mock_responses

        # Run implementation
        report = self.developer.implement_project(plan, spec)

        # 1. Assert workspace files created
        workspace_dir = Path(self.temp_workspace.name)
        self.assertTrue((workspace_dir / "requirements.txt").exists())
        self.assertTrue((workspace_dir / ".env").exists())
        self.assertTrue((workspace_dir / "config.json").exists())
        self.assertTrue((workspace_dir / "schema.sql").exists())
        self.assertTrue((workspace_dir / "api.py").exists())
        self.assertTrue((workspace_dir / "main.py").exists())
        self.assertTrue((workspace_dir / "index.html").exists())
        self.assertTrue((workspace_dir / "implementation_report.md").exists())

        # Check contents
        self.assertEqual(
            (workspace_dir / "requirements.txt").read_text(encoding="utf-8"),
            "fastapi>=0.100.0",
        )

        # 2. Verify return types and model structure
        self.assertEqual(report.project_id, "test-project-123")
        self.assertEqual(report.status, "SUCCESS")
        # 7 generative files + 1 markdown report
        self.assertEqual(len(report.files), 8)

        # 3. Assert events were published to the event bus
        published_event_types = [
            call[0][0].event_type for call in self.mock_event_bus.publish.call_args_list
        ]
        self.assertIn("developer.started", published_event_types)
        self.assertIn("developer.file_generated", published_event_types)
        self.assertIn("developer.progress_updated", published_event_types)
        self.assertIn("developer.file_written", published_event_types)
        self.assertIn("developer.completed", published_event_types)

        # 4. Assert memory storage
        runtime_report = self.memory.runtime.get_project_state("implementation_report")
        project_report = self.memory.project.get_metadata("implementation_report")
        self.assertIsNotNone(runtime_report)
        self.assertIsNotNone(project_report)
        self.assertEqual(runtime_report["project_id"], "test-project-123")

    def test_validation_missing_project_plan(self) -> None:
        """Verifies ValidationError is raised when ProjectPlan is invalid."""
        plan = None
        _, spec = self._get_mock_plan_and_spec()

        with self.assertRaises(DeveloperValidationError):
            self.developer.implement_project(plan, spec)  # type: ignore[arg-type]

    def test_validation_missing_architecture(self) -> None:
        """Verifies ValidationError is raised when ArchitectureSpecification is invalid."""
        plan, _ = self._get_mock_plan_and_spec()
        spec = None

        with self.assertRaises(DeveloperValidationError):
            self.developer.implement_project(plan, spec)  # type: ignore[arg-type]

    def test_validation_missing_project_id(self) -> None:
        """Verifies ValidationError is raised when project_id is empty."""
        plan, spec = self._get_mock_plan_and_spec()
        spec.project_id = ""

        with self.assertRaises(DeveloperValidationError):
            self.developer.implement_project(plan, spec)

    def test_pipeline_failure_rollback(self) -> None:
        """Verifies transaction rollback and clean workspace if LLM fails halfway."""
        plan, spec = self._get_mock_plan_and_spec()

        # Let the second generator step fail due to empty/malformed LLM output
        mock_responses = [
            ModelResponse(
                text='{"files": [{"path": "requirements.txt", "content": "fastapi", "file_type": "dependency"}]}',
                raw_response={},
                model_name="mock-model",
            ),
            ModelResponse(
                text="not json format", raw_response={}, model_name="mock-model"
            ),
        ]
        self.mock_router.generate.side_effect = mock_responses

        with self.assertRaises(DeveloperError):
            self.developer.implement_project(plan, spec)

        # Assert no files were written to workspace
        workspace_dir = Path(self.temp_workspace.name)
        workspace_files = list(workspace_dir.glob("**/*"))
        # Directory should remain empty (or just the directory itself)
        files_only = [f for f in workspace_files if f.is_file()]
        self.assertEqual(len(files_only), 0)

        # Assert developer.failed event was published
        published_event_types = [
            call[0][0].event_type for call in self.mock_event_bus.publish.call_args_list
        ]
        self.assertIn("developer.failed", published_event_types)

    def test_workspace_write_failure_rollback(self) -> None:
        """Verifies transaction rollback and clean workspace if writing fails (e.g. security block)."""
        plan, spec = self._get_mock_plan_and_spec()

        # Simulate a write escape/security validation error by requesting file path escaping workspace
        mock_responses = [
            ModelResponse(
                text='{"files": [{"path": "../outside.txt", "content": "escaped", "file_type": "dependency"}]}',
                raw_response={},
                model_name="mock-model",
            ),
        ]
        self.mock_router.generate.side_effect = mock_responses

        # Running this should raise DeveloperError or DeveloperWriteError
        with self.assertRaises(DeveloperError):
            self.developer.implement_project(plan, spec)

        # Assert workspace remained clean
        workspace_dir = Path(self.temp_workspace.name)
        workspace_files = list(workspace_dir.glob("**/*"))
        files_only = [f for f in workspace_files if f.is_file()]
        self.assertEqual(len(files_only), 0)
