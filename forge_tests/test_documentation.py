"""
Unit and integration tests for the ForgeAI Documentation Plugin.
"""

import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.model_router.service import ModelRouterService, ModelResponse
from forge_core.event_bus.service import EventBusService
from forge_core.memory.service import MemoryService, ForgeAIMemoryService
from forge_core.configuration.service import ConfigurationService
from forge_core.configuration.models import (
    ForgeConfig,
    SystemSettings,
    ModelSettings,
    PluginSettings,
)

from forge_plugins.planner.models import ProjectPlan, ProjectGoal
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport, GeneratedFile
from forge_plugins.tester.models import TestReport, GeneratedTestFile

from forge_plugins.documentation.service import ForgeAIDocumentation
from forge_plugins.documentation.models import GeneratedDocFile, DocumentationReport
from forge_plugins.documentation.exceptions import (
    DocValidationError,
    DocumentationError,
    DocInferenceError,
    DocWriteError,
)
from forge_plugins.documentation.validators.doc_validator import DocValidator
from forge_plugins.documentation.writers.doc_workspace_writer import DocWorkspaceWriter
from forge_plugins.documentation.utils.doc_pipeline import (
    DocContext,
    DocPipeline,
    DocPipelineStep,
)
from forge_plugins.documentation.utils.prompt_helper import load_prompt_and_generate
from forge_plugins.documentation.plugin import DocumentationPlugin


class TestDocumentationPlugin(unittest.TestCase):
    """Test suite verifying components, lifecycles, and pipelines of the Documentation Plugin."""

    def setUp(self) -> None:
        self.temp_workspace = tempfile.TemporaryDirectory()

        # Mock Kernel services
        self.mock_router = MagicMock(spec=ModelRouterService)
        self.mock_event_bus = MagicMock(spec=EventBusService)
        self.mock_config = MagicMock(spec=ConfigurationService)
        self.memory = ForgeAIMemoryService(db_path=":memory:")
        self.memory.initialize()

        # System settings mock
        self.sys_settings = SystemSettings(
            workspace_dir=self.temp_workspace.name, log_level="INFO"
        )
        self.mock_config.get_system_settings.return_value = self.sys_settings

        # Setup config schema mocks
        self.full_config = ForgeConfig(
            version="1.0",
            schema_version="1.0",
            system=self.sys_settings,
            models=ModelSettings(
                provider="mock",
                default_model="mock-model",
                base_url="http://localhost:11434",
                temperature=0.7,
                max_tokens=4096,
            ),
            plugins=PluginSettings(),
        )
        self.mock_config.get_full_config.return_value = self.full_config

        # Registry mock
        self.registry = ServiceRegistry()
        self.registry.register(ModelRouterService, self.mock_router)  # type: ignore[type-abstract]
        self.registry.register(EventBusService, self.mock_event_bus)  # type: ignore[type-abstract]
        self.registry.register(MemoryService, self.memory)  # type: ignore[type-abstract]
        self.registry.register(ConfigurationService, self.mock_config)  # type: ignore[type-abstract]

        # Documentation service instance
        self.doc_service = ForgeAIDocumentation(self.registry)

    def tearDown(self) -> None:
        self.temp_workspace.cleanup()

    def _get_mock_artifacts(self) -> tuple:
        """Helper to create dummy inputs representing the completed pipeline."""
        plan = ProjectPlan(
            goal=ProjectGoal(
                goal="Todo API", description="A FastAPI Todo List application."
            ),
            requirements=[],
            clarifications=[],
            milestones=[],
            tasks=[],
            estimated_order=[],
        )
        spec = ArchitectureSpecification(
            project_id="todo-api",
            directory_structure="src/\n  main.py",
            modules=[],
            database_design=[],
            decisions=[],
            adrs=[],
        )
        report = ImplementationReport(
            project_id="todo-api",
            files=[
                GeneratedFile(
                    path="src/main.py", content="print('hello')", file_type="backend"
                )
            ],
            status="SUCCESS",
            summary="",
        )
        test_report = TestReport(
            project_id="todo-api",
            test_files=[
                GeneratedTestFile(
                    path="tests/test_unit.py",
                    content="def test_ok(): pass",
                    test_type="unit",
                )
            ],
            status="SUCCESS",
            summary="",
        )
        return plan, spec, report, test_report

    def test_doc_validator_complete_inputs(self) -> None:
        """Verifies DocValidator accepts complete, correct input reports."""
        validator = DocValidator()
        plan, spec, report, test_report = self._get_mock_artifacts()

        # Valid execution should run without raising exceptions
        validator.validate(plan, spec, report, test_report, self.temp_workspace.name)

    def test_doc_validator_missing_inputs(self) -> None:
        """Verifies DocValidator rejects missing or incomplete input fields."""
        validator = DocValidator()
        plan, spec, report, test_report = self._get_mock_artifacts()

        with self.assertRaises(DocValidationError):
            validator.validate(None, spec, report, test_report, self.temp_workspace.name)  # type: ignore[arg-type]

        with self.assertRaises(DocValidationError):
            validator.validate(plan, None, report, test_report, self.temp_workspace.name)  # type: ignore[arg-type]

        with self.assertRaises(DocValidationError):
            validator.validate(plan, spec, None, test_report, self.temp_workspace.name)  # type: ignore[arg-type]

        with self.assertRaises(DocValidationError):
            validator.validate(plan, spec, report, None, self.temp_workspace.name)  # type: ignore[arg-type]

        with self.assertRaises(DocValidationError):
            validator.validate(plan, spec, report, test_report, "")

        with self.assertRaises(DocValidationError):
            validator.validate(
                plan, spec, report, test_report, "nonexistent_workspace_folder_123"
            )

    def test_doc_pipeline_step_progress_broadcasting(self) -> None:
        """Verifies DocPipeline triggers step starts, completes, and calculates correct percentage updates."""

        class DummyStep(DocPipelineStep):
            @property
            def name(self) -> str:
                return "Dummy Step"

            def run(self, context: DocContext) -> None:
                context.generated_docs.append(
                    GeneratedDocFile(
                        path="docs/dummy.md", content="Content", category="user"
                    )
                )

        plan, spec, report, test_report = self._get_mock_artifacts()
        context = DocContext(
            project_plan=plan,
            architecture=spec,
            implementation_report=report,
            test_report=test_report,
            workspace=self.temp_workspace.name,
            model_router=self.mock_router,
            event_bus=self.mock_event_bus,
            configuration=self.full_config,
            logger=logging.getLogger("test"),
        )

        pipeline = DocPipeline([DummyStep()], self.mock_event_bus)
        pipeline.run(context)

        self.assertEqual(context.progress_percentage, 100.0)
        self.assertEqual(len(context.generated_docs), 1)
        self.assertTrue(self.mock_event_bus.publish.called)

    def test_prompt_helper_missing_file(self) -> None:
        """Verifies load_prompt_and_generate throws DocInferenceError on missing templates."""
        plan, spec, report, test_report = self._get_mock_artifacts()
        context = DocContext(
            project_plan=plan,
            architecture=spec,
            implementation_report=report,
            test_report=test_report,
            workspace=self.temp_workspace.name,
            model_router=self.mock_router,
            event_bus=self.mock_event_bus,
            configuration=self.full_config,
            logger=logging.getLogger("test"),
        )

        with self.assertRaises(DocInferenceError):
            load_prompt_and_generate(
                context, "non_existent_prompt_template_file", "project"
            )

    def test_prompt_helper_json_syntax_failure(self) -> None:
        """Verifies load_prompt_and_generate maps malformed JSON response to DocInferenceError."""
        plan, spec, report, test_report = self._get_mock_artifacts()
        context = DocContext(
            project_plan=plan,
            architecture=spec,
            implementation_report=report,
            test_report=test_report,
            workspace=self.temp_workspace.name,
            model_router=self.mock_router,
            event_bus=self.mock_event_bus,
            configuration=self.full_config,
            logger=logging.getLogger("test"),
        )

        # Mock malformed LLM response
        self.mock_router.generate.return_value = ModelResponse(
            text="invalid json string payload", raw_response={}, model_name="mock-model"
        )

        with self.assertRaises(DocInferenceError):
            load_prompt_and_generate(context, "project", "project")

    def test_doc_workspace_writer_rollback(self) -> None:
        """Verifies DocWorkspaceWriter restores backups and cleans workspace on write errors."""
        writer = DocWorkspaceWriter(self.mock_event_bus)

        # Pre-populate workspace with an existing file
        workspace_path = Path(self.temp_workspace.name)
        existing_doc = workspace_path / "docs" / "test_existing.md"
        existing_doc.parent.mkdir(parents=True, exist_ok=True)
        existing_doc.write_text("# Existing Doc", encoding="utf-8")

        files = [
            GeneratedDocFile(
                path="docs/test_existing.md",
                content="# Updated Doc",
                category="project",
            ),
            GeneratedDocFile(
                path="docs/test_fail.md", content="# Failed write", category="project"
            ),
        ]

        # Patch Path.write_text to trigger exception ONLY on the second file write
        original_write = Path.write_text

        def side_effect_write(self_path, data, *args, **kwargs):
            if "test_fail.md" in str(self_path):
                raise IOError("Simulation disk error")
            return original_write(self_path, data, *args, **kwargs)

        with patch.object(
            Path, "write_text", autospec=True, side_effect=side_effect_write
        ):
            with self.assertRaises(DocWriteError):
                writer.write_docs(self.temp_workspace.name, files, "todo-api")

            # Validate rollback restores existing doc and unlinks the written ones
            self.assertEqual(existing_doc.read_text(encoding="utf-8"), "# Existing Doc")
            self.assertFalse((workspace_path / "docs" / "test_fail.md").exists())

    def test_doc_workspace_writer_merge_fallback(self) -> None:
        """Verifies DocWorkspaceWriter falls back to direct overwrite if merge throws exception."""
        writer = DocWorkspaceWriter(self.mock_event_bus)
        self.mock_router.generate.side_effect = Exception("Model router unavailable")

        merged = writer._merge_doc_files("# existing", "# new", self.mock_router)
        self.assertEqual(merged, "# new")

    def test_doc_workspace_writer_existing_file_read_failure(self) -> None:
        """Verifies DocWorkspaceWriter handles permission read failures on backup gracefully."""
        writer = DocWorkspaceWriter(self.mock_event_bus)
        workspace_dir = Path(self.temp_workspace.name)
        (workspace_dir / "docs").mkdir(parents=True, exist_ok=True)
        existing_file = workspace_dir / "docs" / "test_unreadable.md"
        existing_file.write_text("# content", encoding="utf-8")

        files = [
            GeneratedDocFile(
                path="docs/test_unreadable.md",
                content="# new content",
                category="project",
            )
        ]

        # Patch Path.read_text to raise an exception, verifying backup state continues safely
        with patch.object(Path, "read_text", side_effect=IOError("Permission denied")):
            writer.write_docs(self.temp_workspace.name, files, "todo-api")

        # Verify content was still written successfully
        self.assertEqual(existing_file.read_text(encoding="utf-8"), "# new content")

    def test_doc_workspace_writer_rollback_unlink_failure(self) -> None:
        """Verifies DocWorkspaceWriter rollback handles deletion and restoration errors cleanly without crashing."""
        writer = DocWorkspaceWriter(self.mock_event_bus)

        # Mock Path.write_text to trigger rollback on the second write, unlink locked during cleanup
        with patch.object(
            Path, "write_text", autospec=True, side_effect=[None, IOError("Disk Full")]
        ):
            with patch.object(Path, "unlink", side_effect=IOError("File locked")):
                with self.assertRaises(DocWriteError):
                    writer.write_docs(
                        self.temp_workspace.name,
                        [
                            GeneratedDocFile(
                                path="docs/test_rollback_err.md",
                                content="# 1",
                                category="project",
                            ),
                            GeneratedDocFile(
                                path="docs/test_rollback_err2.md",
                                content="# 2",
                                category="project",
                            ),
                        ],
                        "todo-api",
                    )

    def test_service_validation_failure(self) -> None:
        """Verifies DocumentationService registers validation errors and raises exceptions."""
        plan, spec, report, test_report = self._get_mock_artifacts()

        # Set workspace parameter to nonexistent path
        self.sys_settings = SystemSettings(
            workspace_dir="nonexistent_folder_path_123", log_level="INFO"
        )
        self.mock_config.get_system_settings.return_value = self.sys_settings

        with self.assertRaises(DocValidationError):
            self.doc_service.document_project(plan, spec, report, test_report)

        self.assertTrue(self.mock_event_bus.publish.called)

    def test_service_inference_error_pipeline(self) -> None:
        """Verifies DocumentationService maps pipeline steps inference error to DocInferenceError."""
        plan, spec, report, test_report = self._get_mock_artifacts()

        # Mock router generate to raise exception to trigger step failures
        self.mock_router.generate.side_effect = Exception("offline model")

        with self.assertRaises(DocInferenceError):
            self.doc_service.document_project(plan, spec, report, test_report)

    def test_service_unexpected_config_resolution_failure(self) -> None:
        """Verifies DocumentationService throws DocumentationError when settings manager throws Exception."""
        plan, spec, report, test_report = self._get_mock_artifacts()
        self.mock_config.get_system_settings.side_effect = Exception(
            "System Config Error"
        )

        with self.assertRaises(DocumentationError):
            self.doc_service.document_project(plan, spec, report, test_report)

    def test_service_unexpected_write_exception(self) -> None:
        """Verifies DocumentationService reports write failures cleanly."""
        plan, spec, report, test_report = self._get_mock_artifacts()

        mock_responses = [
            ModelResponse(text='{"files": []}', raw_response={}, model_name="mock")
            for _ in range(6)
        ]
        self.mock_router.generate.side_effect = mock_responses

        # Patch write_docs to raise generic exception
        with patch.object(
            self.doc_service.writer,
            "write_docs",
            side_effect=RuntimeError("Disk crash"),
        ):
            with self.assertRaises(DocWriteError):
                self.doc_service.document_project(plan, spec, report, test_report)

    def test_service_memory_storage_exception(self) -> None:
        """Verifies DocumentationService handles database locks inside memory service safely."""
        plan, spec, report, test_report = self._get_mock_artifacts()

        # Mock standard LLM responses for the 6 generators
        mock_responses = [
            ModelResponse(text='{"files": []}', raw_response={}, model_name="mock")
            for _ in range(6)
        ]
        self.mock_router.generate.side_effect = mock_responses

        # Patch memory service to raise an exception
        with patch.object(
            self.memory.runtime,
            "set_project_state",
            side_effect=Exception("Database locked"),
        ):
            doc_report = self.doc_service.document_project(
                plan, spec, report, test_report
            )
            self.assertEqual(doc_report.status, "SUCCESS")

    def test_plugin_lifecycle(self) -> None:
        """Verifies the DocumentationPlugin adapter registration and shutdown routines."""
        plugin = DocumentationPlugin()
        self.assertEqual(plugin.name, "documentation")
        self.assertEqual(plugin.version, "1.0.0")

        mock_registry = MagicMock(spec=ServiceRegistry)
        plugin.initialize(mock_registry)

        # Resolve calls
        self.assertTrue(mock_registry.register.called)

        # Shutdown
        plugin.shutdown()

    def test_doc_validator_inner_fields(self) -> None:
        """Verifies DocValidator flags invalid inner schema fields."""
        import dataclasses

        validator = DocValidator()
        plan, spec, report, test_report = self._get_mock_artifacts()

        # 1. Invalid plan goal
        bad_plan = dataclasses.replace(plan, goal=None)
        with self.assertRaises(DocValidationError):
            validator.validate(
                bad_plan, spec, report, test_report, self.temp_workspace.name
            )

        # 2. Invalidate spec project ID
        bad_spec = dataclasses.replace(spec, project_id="")
        with self.assertRaises(DocValidationError):
            validator.validate(
                plan, bad_spec, report, test_report, self.temp_workspace.name
            )

        # 3. Invalidate report files
        bad_report = dataclasses.replace(report, files=[])
        with self.assertRaises(DocValidationError):
            validator.validate(
                plan, spec, bad_report, test_report, self.temp_workspace.name
            )

    def test_models_from_dict(self) -> None:
        """Verifies from_dict and to_dict deserialization workflows on models."""
        # 1. GeneratedDocFile
        df_dict = {"path": "docs/readme.md", "content": "text", "category": "project"}
        df = GeneratedDocFile.from_dict(df_dict)
        self.assertEqual(df.path, "docs/readme.md")
        self.assertEqual(df.category, "project")
        self.assertEqual(df.to_dict(), df_dict)

        # 2. DocumentationReport
        rep_dict = {
            "project_id": "test-p",
            "doc_files": [df_dict],
            "status": "SUCCESS",
            "summary": "Index markdown",
        }
        rep = DocumentationReport.from_dict(rep_dict)
        self.assertEqual(rep.project_id, "test-p")
        self.assertEqual(rep.status, "SUCCESS")
        self.assertEqual(rep.to_dict(), rep_dict)

    def test_prompt_helper_read_failure(self) -> None:
        """Verifies load_prompt_and_generate throws DocInferenceError on read template exceptions."""
        plan, spec, report, test_report = self._get_mock_artifacts()
        context = DocContext(
            project_plan=plan,
            architecture=spec,
            implementation_report=report,
            test_report=test_report,
            workspace=self.temp_workspace.name,
            model_router=self.mock_router,
            event_bus=self.mock_event_bus,
            configuration=self.full_config,
            logger=logging.getLogger("test"),
        )

        with patch("pathlib.Path.read_text", side_effect=IOError("Template lock")):
            with self.assertRaises(DocInferenceError):
                load_prompt_and_generate(context, "project", "project")

    def test_prompt_helper_malformed_items(self) -> None:
        """Verifies load_prompt_and_generate handles malformed dictionary structures from LLM."""
        plan, spec, report, test_report = self._get_mock_artifacts()
        context = DocContext(
            project_plan=plan,
            architecture=spec,
            implementation_report=report,
            test_report=test_report,
            workspace=self.temp_workspace.name,
            model_router=self.mock_router,
            event_bus=self.mock_event_bus,
            configuration=self.full_config,
            logger=logging.getLogger("test"),
        )

        # Mock invalid files structure (e.g. entry without content or missing properties)
        self.mock_router.generate.return_value = ModelResponse(
            text='{"files": [{"path": "docs/README.md", "content": null}]}',
            raw_response={},
            model_name="mock",
        )

        with self.assertRaises(DocInferenceError):
            load_prompt_and_generate(context, "project", "project")

    def test_doc_workspace_writer_merge_success(self) -> None:
        """Verifies DocWorkspaceWriter successfully performs LLM-based merges."""
        writer = DocWorkspaceWriter(self.mock_event_bus)
        self.mock_router.generate.return_value = ModelResponse(
            text="# Consolidated Doc", raw_response={}, model_name="mock"
        )
        merged = writer._merge_doc_files("# existing", "# new", self.mock_router)
        self.assertEqual(merged, "# Consolidated Doc")

    def test_doc_workspace_writer_manifest_write_failure(self) -> None:
        """Verifies DocWorkspaceWriter catches and logs manifest writing errors without crashing."""
        writer = DocWorkspaceWriter(self.mock_event_bus)
        workspace_dir = Path(self.temp_workspace.name)

        files = [
            GeneratedDocFile(path="docs/test.md", content="# text", category="project")
        ]

        # Patch _write_manifest directly to simulate a filesystem failure during manifest write.
        # This avoids Python 3.13 argument-binding issues when patching Path.write_text.
        with patch.object(
            writer,
            "_write_manifest",
            side_effect=IOError("ReadOnly filesystem"),
        ):
            # write_docs catches the manifest IOError internally and logs it — should NOT raise
            writer.write_docs(self.temp_workspace.name, files, "todo-api")

        # The doc file itself should still exist (written before manifest attempt)
        self.assertTrue((workspace_dir / "docs" / "test.md").exists())
