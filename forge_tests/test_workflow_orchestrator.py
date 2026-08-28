import unittest
import time
import tempfile
from unittest.mock import MagicMock
from pathlib import Path

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.event_bus.event_bus import ForgeAIEventBus
from forge_core.event_bus.service import EventBusService
from forge_core.memory.service import ForgeAIMemoryService, MemoryService
from forge_core.configuration.config_manager import ConfigurationManager
from forge_core.configuration.service import ConfigurationService

from forge_core.workflow.models import (
    WorkflowState,
    WorkflowType,
    WorkflowStage,
    Workflow,
)
from forge_core.workflow.exceptions import (
    WorkflowValidationError,
    WorkflowExecutionError,
    WorkflowStateError,
)
from forge_core.workflow.state_machine import WorkflowStateMachine
from forge_core.workflow.service import ForgeAIWorkflowService

from forge_plugins.planner.service import PlannerService
from forge_plugins.architect.service import ArchitectService
from forge_plugins.developer.service import DeveloperService
from forge_plugins.tester.service import TesterService
from forge_plugins.documentation.service import DocumentationService
from forge_plugins.git.service import GitService
from forge_plugins.security.service import SecurityService
from forge_plugins.reviewer.service import ReviewerService


class TestWorkflowOrchestrator(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ServiceRegistry()

        self.temp_dir = tempfile.TemporaryDirectory()
        self.defaults_path = Path(self.temp_dir.name) / "defaults.json"

        import json

        real_defaults = json.loads(
            Path("config/defaults.json").read_text(encoding="utf-8")
        )
        real_defaults["system"]["workspace_dir"] = self.temp_dir.name.replace("\\", "/")
        self.defaults_path.write_text(json.dumps(real_defaults), encoding="utf-8")

        self.config_manager = ConfigurationManager(
            config_path="forge.json", defaults_path=str(self.defaults_path)
        )
        self.registry.register(ConfigurationService, self.config_manager)  # type: ignore[type-abstract]

        self.event_bus = ForgeAIEventBus()
        self.registry.register(EventBusService, self.event_bus)  # type: ignore[type-abstract]
        self.event_bus.initialize()

        self.memory = ForgeAIMemoryService(
            db_path=str(Path(self.temp_dir.name) / "project_memory.db")
        )
        self.registry.register(MemoryService, self.memory)  # type: ignore[type-abstract]
        self.memory.initialize()

        self.workflow_service = ForgeAIWorkflowService(self.registry)
        self.workflow_service.initialize()

        self.mock_planner = MagicMock(spec=PlannerService)
        self.mock_architect = MagicMock(spec=ArchitectService)
        self.mock_developer = MagicMock(spec=DeveloperService)
        self.mock_tester = MagicMock(spec=TesterService)
        self.mock_documentation = MagicMock(spec=DocumentationService)
        self.mock_git = MagicMock(spec=GitService)
        self.mock_security = MagicMock(spec=SecurityService)
        self.mock_reviewer = MagicMock(spec=ReviewerService)

        self.registry.register(PlannerService, self.mock_planner)
        self.registry.register(ArchitectService, self.mock_architect)
        self.registry.register(DeveloperService, self.mock_developer)
        self.registry.register(TesterService, self.mock_tester)
        self.registry.register(DocumentationService, self.mock_documentation)
        self.registry.register(GitService, self.mock_git)
        self.registry.register(SecurityService, self.mock_security)
        self.registry.register(ReviewerService, self.mock_reviewer)

    def tearDown(self) -> None:
        self.workflow_service.shutdown()
        self.memory.shutdown()
        self.event_bus.shutdown()
        self.temp_dir.cleanup()

    def test_state_machine_invalid_transitions(self) -> None:
        """Verifies state machine transitions raise error on invalid pathways."""
        workflow = Workflow(
            id="test-id",
            name="test-workflow",
            type=WorkflowType.BUILD_ONLY,
            state=WorkflowState.PENDING,
            stages=[],
        )

        WorkflowStateMachine.transition(workflow, WorkflowState.RUNNING)
        self.assertEqual(workflow.state, WorkflowState.RUNNING)

        with self.assertRaises(WorkflowStateError):
            WorkflowStateMachine.transition(workflow, WorkflowState.PENDING)

        WorkflowStateMachine.transition(workflow, WorkflowState.RUNNING)

    def test_full_engineering_workflow_success(self) -> None:
        """Verifies successful end-to-end execution of a full engineering workflow."""
        mock_plan = MagicMock()
        mock_spec = MagicMock()
        mock_dev_report = MagicMock()
        mock_test_report = MagicMock()
        mock_doc_report = MagicMock()
        mock_security_report = MagicMock()
        mock_review_report = MagicMock()
        mock_git_report = MagicMock()

        self.mock_planner.plan_project.return_value = mock_plan
        self.mock_architect.design_architecture.return_value = mock_spec
        self.mock_developer.implement_project.return_value = mock_dev_report
        self.mock_tester.test_project.return_value = mock_test_report
        self.mock_documentation.document_project.return_value = mock_doc_report
        self.mock_security.audit_project.return_value = mock_security_report
        self.mock_reviewer.review_project.return_value = mock_review_report
        self.mock_git.commit_project.return_value = mock_git_report

        workflow = self.workflow_service.create_workflow(
            WorkflowType.FULL_ENGINEERING,
            "HMS Workflow",
            "Build a Hospital Management System",
        )

        events_emitted = []
        self.event_bus.subscribe("*", lambda e: events_emitted.append(e.event_type))

        report = self.workflow_service.run_workflow(workflow)

        self.mock_planner.plan_project.assert_called_once_with(
            "Build a Hospital Management System"
        )
        self.mock_architect.design_architecture.assert_called_once_with(mock_plan)
        self.mock_developer.implement_project.assert_called_once_with(
            mock_plan, mock_spec
        )
        self.mock_tester.test_project.assert_called_once_with(
            mock_plan, mock_spec, mock_dev_report
        )
        self.mock_documentation.document_project.assert_called_once_with(
            mock_plan, mock_spec, mock_dev_report, mock_test_report
        )
        self.mock_security.audit_project.assert_called_once_with(
            mock_plan, mock_spec, mock_dev_report, mock_test_report, mock_doc_report
        )
        self.mock_reviewer.review_project.assert_called_once_with(
            mock_plan, mock_spec, mock_dev_report, mock_test_report, mock_doc_report
        )
        self.mock_git.commit_project.assert_called_once_with(
            mock_plan,
            mock_spec,
            mock_dev_report,
            mock_test_report,
            mock_doc_report,
            security_report=mock_security_report,
        )

        self.assertEqual(report["status"], "COMPLETED")
        self.assertEqual(report["progress"], 100.0)
        self.assertEqual(len(report["stages"]), 8)
        self.assertTrue(Path(self.temp_dir.name, "workflow_report.json").exists())
        self.assertTrue(Path(self.temp_dir.name, "workflow_summary.md").exists())

        loaded = self.workflow_service.load_workflow(workflow.id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.state, WorkflowState.COMPLETED)

        self.assertIn("workflow.started", events_emitted)
        self.assertIn("workflow.stage_started", events_emitted)
        self.assertIn("workflow.stage_completed", events_emitted)
        self.assertIn("workflow.completed", events_emitted)

    def test_custom_workflow_execution_and_resuming(self) -> None:
        """Verifies custom workflow configuration, task execution, and state resumes."""
        stage1 = WorkflowStage(
            name="planner",
            service_interface=PlannerService,
            method_name="plan_project",
        )
        stage2 = WorkflowStage(
            name="architect",
            service_interface=ArchitectService,
            method_name="design_architecture",
        )

        workflow = self.workflow_service.create_workflow(
            WorkflowType.CUSTOM,
            "Custom Short Flow",
            "Generate short flow blueprint",
            custom_stages=[stage1, stage2],
        )

        mock_plan = MagicMock()
        mock_spec = MagicMock()
        self.mock_planner.plan_project.return_value = mock_plan
        self.mock_architect.design_architecture.return_value = mock_spec

        self.mock_architect.design_architecture.side_effect = RuntimeError(
            "Design error"
        )

        with self.assertRaises(WorkflowExecutionError):
            self.workflow_service.run_workflow(workflow)

        self.assertEqual(workflow.state, WorkflowState.FAILED)
        self.assertEqual(workflow.stages[0].status, WorkflowState.COMPLETED)
        self.assertEqual(workflow.stages[1].status, WorkflowState.FAILED)

        loaded = self.workflow_service.load_workflow(workflow.id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.state, WorkflowState.FAILED)

        loaded.state = WorkflowState.PENDING
        self.mock_architect.design_architecture.side_effect = None
        self.mock_planner.plan_project.reset_mock()
        self.mock_architect.design_architecture.reset_mock()

        report = self.workflow_service.run_workflow(loaded)

        self.mock_planner.plan_project.assert_not_called()
        self.mock_architect.design_architecture.assert_called_once()
        self.assertEqual(report["status"], "COMPLETED")

    def test_optional_stage_failures(self) -> None:
        """Verifies optional stage failure does not abort the workflow execution."""
        stage1 = WorkflowStage(
            name="planner",
            service_interface=PlannerService,
            method_name="plan_project",
            critical=True,
        )
        stage2 = WorkflowStage(
            name="documentation",
            service_interface=DocumentationService,
            method_name="document_project",
            critical=False,
            optional=True,
            retry_count=0,
        )

        workflow = self.workflow_service.create_workflow(
            WorkflowType.CUSTOM,
            "Optional Failure Flow",
            "Check optional failure handling",
            custom_stages=[stage1, stage2],
        )

        mock_plan = MagicMock()
        self.mock_planner.plan_project.return_value = mock_plan
        self.mock_documentation.document_project.side_effect = Exception(
            "Doc writer fail"
        )

        report = self.workflow_service.run_workflow(workflow)

        self.mock_planner.plan_project.assert_called_once()
        self.mock_documentation.document_project.assert_called_once()
        self.assertEqual(report["status"], "COMPLETED")
        self.assertEqual(report["stages"][1]["status"], "FAILED")

    def test_stage_retry_and_timeout(self) -> None:
        """Verifies retry mechanism executes up to retry limits and timeout policies fail."""
        stage = WorkflowStage(
            name="planner",
            service_interface=PlannerService,
            method_name="plan_project",
            retry_count=2,
            retry_delay=0.1,
            timeout=0.5,
        )

        workflow = self.workflow_service.create_workflow(
            WorkflowType.CUSTOM,
            "Retry Fail Flow",
            "Verify retry constraints",
            custom_stages=[stage],
        )

        self.mock_planner.plan_project.side_effect = ValueError("Inference error")

        with self.assertRaises(WorkflowExecutionError):
            self.workflow_service.run_workflow(workflow)

        self.assertEqual(self.mock_planner.plan_project.call_count, 3)

        stage_timeout = WorkflowStage(
            name="planner",
            service_interface=PlannerService,
            method_name="plan_project",
            retry_count=0,
            retry_delay=0.1,
            timeout=0.01,
        )
        workflow_timeout = self.workflow_service.create_workflow(
            WorkflowType.CUSTOM,
            "Timeout Flow",
            "Verify timeout limits",
            custom_stages=[stage_timeout],
        )

        def slow_action(*args, **kwargs):
            time.sleep(0.1)
            return MagicMock()

        self.mock_planner.plan_project.side_effect = slow_action

        with self.assertRaises(WorkflowExecutionError):
            self.workflow_service.run_workflow(workflow_timeout)

    def test_running_status_persisted_before_blocking_call(self) -> None:
        """
        A client polling GET /workflows/{id} mid-stage must see RUNNING, not
        PENDING, for the whole duration of a long-running (e.g. real LLM)
        call. Regression test: status used to only get saved at a stage's
        start/end boundaries, so an in-flight stage was invisible until it
        finished - found via a live run against a real local model where the
        UI appeared to make no progress for several minutes.
        """
        observed_status = {}

        def check_persisted_state_mid_call(*args, **kwargs):
            reloaded = self.workflow_service.load_workflow(workflow.id)
            observed_status["status"] = (
                reloaded.stages[0].status.value if reloaded else None
            )
            return MagicMock()

        self.mock_planner.plan_project.side_effect = check_persisted_state_mid_call

        stage = WorkflowStage(
            name="planner",
            service_interface=PlannerService,
            method_name="plan_project",
        )
        workflow = self.workflow_service.create_workflow(
            WorkflowType.CUSTOM,
            "Observability Check",
            "Verify mid-stage status",
            custom_stages=[stage],
        )

        self.workflow_service.run_workflow(workflow)

        self.assertEqual(observed_status["status"], "RUNNING")

    def test_create_workflow_validation_checks(self) -> None:
        """Verifies create_workflow validates input configuration properly."""
        with self.assertRaises(WorkflowValidationError):
            self.workflow_service.create_workflow(
                WorkflowType.CUSTOM,
                "Custom Bad Flow",
                "Needs custom stage list",
                custom_stages=None,
            )

        self.assertIsNone(self.workflow_service.load_workflow("non-existent-uuid"))

    def test_cancel_active_workflow(self) -> None:
        """Verifies cancelling workflow state transitions correctly."""
        workflow = self.workflow_service.create_workflow(
            WorkflowType.BUILD_ONLY,
            "Cancel test",
            "Goal",
        )
        self.workflow_service.cancel_workflow(workflow)
        self.assertEqual(workflow.state, WorkflowState.CANCELLED)

        loaded = self.workflow_service.load_workflow(workflow.id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.state, WorkflowState.CANCELLED)

    def test_workflow_save_error_logs_and_handles(self) -> None:
        """Verifies workflow save catches and logs exceptions without crashing."""
        workflow = self.workflow_service.create_workflow(
            WorkflowType.BUILD_ONLY,
            "Save failure test",
            "Goal",
        )
        from unittest.mock import patch

        with patch.object(
            self.memory.project, "set_metadata", side_effect=RuntimeError("Disk lock")
        ):
            # Should not crash, just log error internally
            assert self.workflow_service._orchestrator is not None
            self.workflow_service._orchestrator._save_workflow(workflow)

    def test_load_workflow_exception_handling(self) -> None:
        """Verifies load_workflow catches exceptions and returns None."""
        from unittest.mock import patch

        with patch.object(
            self.memory.project, "get_metadata", side_effect=RuntimeError("DB corrupt")
        ):
            res = self.workflow_service.load_workflow("some-id")
            self.assertIsNone(res)

    def test_run_workflow_invalid_state_throws(self) -> None:
        """Verifies running a workflow in a non-runnable state (e.g. COMPLETED) raises WorkflowStateError."""
        workflow = self.workflow_service.create_workflow(
            WorkflowType.BUILD_ONLY,
            "Invalid State test",
            "Goal",
        )
        workflow.state = WorkflowState.COMPLETED
        with self.assertRaises(WorkflowStateError):
            self.workflow_service.run_workflow(workflow)

    def test_workflow_stage_already_completed_is_skipped(self) -> None:
        """Verifies run_workflow skips stages that are already COMPLETED."""
        stage1 = WorkflowStage(
            name="planner",
            service_interface=PlannerService,
            method_name="plan_project",
            status=WorkflowState.COMPLETED,
        )
        workflow = self.workflow_service.create_workflow(
            WorkflowType.CUSTOM,
            "Completed skip test",
            "Goal",
            custom_stages=[stage1],
        )
        report = self.workflow_service.run_workflow(workflow)
        self.mock_planner.plan_project.assert_not_called()
        self.assertEqual(report["status"], "COMPLETED")

    def test_default_stages_other_types(self) -> None:
        """Verifies get_default_stages maps other workflow types correctly."""
        from forge_core.workflow.orchestrator import WorkflowOrchestrator

        stages_doc = WorkflowOrchestrator.get_default_stages(
            WorkflowType.DOCUMENTATION_ONLY
        )
        self.assertEqual(len(stages_doc), 1)
        self.assertEqual(stages_doc[0].name, "documentation")

        stages_test = WorkflowOrchestrator.get_default_stages(WorkflowType.TEST_ONLY)
        self.assertEqual(len(stages_test), 1)
        self.assertEqual(stages_test[0].name, "tester")

        stages_delivery = WorkflowOrchestrator.get_default_stages(
            WorkflowType.DELIVERY_ONLY
        )
        self.assertEqual(len(stages_delivery), 1)
        self.assertEqual(stages_delivery[0].name, "git")

        stages_custom = WorkflowOrchestrator.get_default_stages(WorkflowType.CUSTOM)
        self.assertEqual(len(stages_custom), 0)

    def test_reconstruct_context_real_classes(self) -> None:
        """Verifies deserialization and reconstruction of real objects inside context."""
        from forge_plugins.planner.models import ProjectPlan, ProjectGoal
        from forge_plugins.architect.models import ArchitectureSpecification
        from forge_plugins.developer.models import ImplementationReport
        from forge_plugins.tester.models import TestReport
        from forge_plugins.documentation.models import DocumentationReport
        from forge_plugins.git.models import GitReport

        plan = ProjectPlan(
            goal=ProjectGoal("title", "desc"),
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
            project_id="pid",
            directory_structure="",
            modules=[],
            database_design=[],
            decisions=[],
            adrs=[],
            mermaid_diagrams={},
            rationale="",
        )
        impl_rep = ImplementationReport(
            project_id="pid", files=[], summary="", status="SUCCESS"
        )
        test_rep = TestReport(
            project_id="pid",
            test_files=[],
            coverage_summary="",
            status="SUCCESS",
            summary="",
        )
        doc_rep = DocumentationReport(
            project_id="pid", doc_files=[], status="SUCCESS", summary=""
        )
        git_rep = GitReport(
            project_id="pid",
            commits=[],
            tags=[],
            semver=None,
            pr=None,
            changelog="",
            ci_manifest={},
            status="SUCCESS",
            summary="",
        )

        context = {
            "project_plan": plan.to_dict(),
            "architecture_specification": spec.to_dict(),
            "implementation_report": impl_rep.to_dict(),
            "test_report": test_rep.to_dict(),
            "documentation_report": doc_rep.to_dict(),
            "git_report": git_rep.to_dict(),
        }

        from forge_core.workflow.orchestrator import WorkflowOrchestrator

        reconstructed = WorkflowOrchestrator.reconstruct_context(context)

        self.assertIsInstance(reconstructed["project_plan"], ProjectPlan)
        self.assertIsInstance(
            reconstructed["architecture_specification"], ArchitectureSpecification
        )
        self.assertIsInstance(
            reconstructed["implementation_report"], ImplementationReport
        )
        self.assertIsInstance(reconstructed["test_report"], TestReport)
        self.assertIsInstance(
            reconstructed["documentation_report"], DocumentationReport
        )
        self.assertIsInstance(reconstructed["git_report"], GitReport)

    def test_serialize_context_with_to_dict_custom_class(self) -> None:
        """Verifies serialization of custom classes implementing to_dict in models context."""

        class CustomClass:
            def to_dict(self):
                return {"custom": "value"}

        workflow = Workflow(
            id="test-id",
            name="test-workflow",
            type=WorkflowType.BUILD_ONLY,
            state=WorkflowState.PENDING,
            stages=[],
            context={"obj": CustomClass()},
        )
        serialized = workflow.to_dict()
        self.assertEqual(serialized["context"]["obj"], {"custom": "value"})

    def test_report_generation_with_running_stage(self) -> None:
        """Verifies report generator handles running stages without completed_at timestamp."""
        stage = WorkflowStage(
            name="planner",
            service_interface=PlannerService,
            method_name="plan_project",
            status=WorkflowState.RUNNING,
            started_at=time.time() - 10,
        )
        workflow = Workflow(
            id="test-id",
            name="test-workflow",
            type=WorkflowType.BUILD_ONLY,
            state=WorkflowState.RUNNING,
            stages=[stage],
        )
        from forge_core.workflow.workflow_report import WorkflowReportGenerator

        report_data = WorkflowReportGenerator.generate_report(workflow)
        self.assertEqual(report_data["stages"][0]["status"], "RUNNING")
        self.assertGreaterEqual(report_data["stages"][0]["duration_seconds"], 10.0)

        md = WorkflowReportGenerator.generate_markdown_summary(report_data)
        self.assertIn("RUNNING", md)

    def test_custom_stage_mapping_in_run_workflow(self) -> None:
        """Verifies custom stage outputs are mapped with stage_output key and method parameters are mapped from context."""
        mock_custom_service = MagicMock()
        mock_custom_service.run_custom_step = MagicMock(return_value="custom-output")
        self.registry.register(mock_custom_service.__class__, mock_custom_service)

        stage = WorkflowStage(
            name="custom_step",
            service_interface=mock_custom_service.__class__,
            method_name="run_custom_step",
        )

        workflow = self.workflow_service.create_workflow(
            WorkflowType.CUSTOM,
            "Custom Step Flow",
            "Goal",
            custom_stages=[stage],
        )

        workflow.context["arg1"] = "val1"
        report = self.workflow_service.run_workflow(workflow)
        self.assertEqual(report["status"], "COMPLETED")
        self.assertEqual(workflow.context["custom_step_output"], "custom-output")

    def test_run_workflow_generic_exception_transitions_to_failed(self) -> None:
        """Verifies run_workflow transitions to FAILED state and re-raises when generic exceptions occur."""
        stage = WorkflowStage(
            name="planner",
            service_interface=PlannerService,
            method_name="plan_project",
        )
        workflow = self.workflow_service.create_workflow(
            WorkflowType.CUSTOM,
            "Exception Fail Flow",
            "Goal",
            custom_stages=[stage],
        )
        # Induce a TypeError inside run_workflow loop execution (e.g. reconstruct_context failure)
        from unittest.mock import patch

        with patch.object(
            self.workflow_service._orchestrator,
            "reconstruct_context",
            side_effect=TypeError("Data error"),
        ):
            with self.assertRaises(TypeError):
                self.workflow_service.run_workflow(workflow)
        self.assertEqual(workflow.state, WorkflowState.FAILED)
