"""
Workflow Orchestrator running pipeline stages, loading services, and storing states in memory.
"""

import time
import logging
import uuid
from typing import Any, Callable, Dict, List, Optional, Type
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_core.memory.service import MemoryService
from forge_core.configuration.service import ConfigurationService

from .models import Workflow, WorkflowStage, WorkflowState, WorkflowType
from .exceptions import (
    WorkflowValidationError,
    WorkflowExecutionError,
    WorkflowStateError,
)
from .state_machine import WorkflowStateMachine
from .scheduler import WorkflowStageScheduler
from .workflow_report import WorkflowReportGenerator

logger = logging.getLogger("ForgeAI.Workflow.Orchestrator")


class WorkflowOrchestrator:
    """
    Coordinates end-to-end execution, service mapping, and transaction logging for workflows.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        """
        Initializes the orchestrator.

        Args:
            registry (ServiceRegistry): System service container.
        """
        self._registry = registry
        self._scheduler = WorkflowStageScheduler(self._event_bus)

    @property
    def _event_bus(self) -> EventBusService:
        return self._registry.resolve(EventBusService)  # type: ignore[type-abstract]

    @property
    def _memory(self) -> MemoryService:
        return self._registry.resolve(MemoryService)  # type: ignore[type-abstract]

    @property
    def _config(self) -> ConfigurationService:
        return self._registry.resolve(ConfigurationService)  # type: ignore[type-abstract]

    def create_workflow(
        self,
        workflow_type: WorkflowType,
        name: str,
        goal: str,
        custom_stages: Optional[List[WorkflowStage]] = None,
    ) -> Workflow:
        """
        Creates a new workflow instance and registers it in memory storage.
        """
        workflow_id = str(uuid.uuid4())
        stages = []

        if workflow_type == WorkflowType.CUSTOM:
            if not custom_stages:
                raise WorkflowValidationError(
                    "Custom workflows must provide custom_stages."
                )
            stages = custom_stages
        else:
            stages = self.get_default_stages(workflow_type)

        workflow = Workflow(
            id=workflow_id,
            name=name,
            type=workflow_type,
            state=WorkflowState.PENDING,
            stages=stages,
            context={"goal": goal},
        )

        self._save_workflow(workflow)
        logger.info(
            f"Created workflow '{name}' of type {workflow_type.value} with ID: {workflow_id}"
        )
        return workflow

    def run_workflow(self, workflow: Workflow) -> Dict[str, Any]:
        """
        Executes the workflow stages.
        """
        if workflow.state not in (WorkflowState.PENDING, WorkflowState.WAITING):
            raise WorkflowStateError(
                f"Cannot run workflow in state: {workflow.state.value}"
            )

        WorkflowStateMachine.transition(workflow, WorkflowState.RUNNING)
        workflow.updated_at = time.time()
        self._save_workflow(workflow)

        self._event_bus.publish(
            Event(
                event_type="workflow.started",
                data={"workflow_id": workflow.id, "type": workflow.type.value},
            )
        )

        try:
            workflow.context = self.reconstruct_context(workflow.context)

            while workflow.current_stage_index < len(workflow.stages):
                stage = workflow.stages[workflow.current_stage_index]

                if stage.status == WorkflowState.COMPLETED:
                    workflow.current_stage_index += 1
                    workflow.progress = round(
                        (workflow.current_stage_index / len(workflow.stages)) * 100.0, 2
                    )
                    self._save_workflow(workflow)
                    continue

                action = self._bind_stage_action(workflow, stage)

                try:
                    result = self._scheduler.execute_stage(workflow, stage, action)

                    if stage.name == "planner":
                        workflow.context["project_plan"] = result
                    elif stage.name == "architect":
                        workflow.context["architecture_specification"] = result
                    elif stage.name == "developer":
                        workflow.context["implementation_report"] = result
                    elif stage.name == "tester":
                        workflow.context["test_report"] = result
                    elif stage.name == "documentation":
                        workflow.context["documentation_report"] = result
                    elif stage.name == "security":
                        workflow.context["security_report"] = result
                    elif stage.name == "reviewer":
                        workflow.context["review_report"] = result
                    elif stage.name == "git":
                        workflow.context["git_report"] = result
                    else:
                        workflow.context[f"{stage.name}_output"] = result

                    workflow.current_stage_index += 1
                    workflow.progress = round(
                        (workflow.current_stage_index / len(workflow.stages)) * 100.0, 2
                    )
                    self._save_workflow(workflow)

                except Exception as stage_err:
                    workflow.errors[stage.name] = str(stage_err)
                    self._save_workflow(workflow)

                    if stage.critical:
                        WorkflowStateMachine.transition(workflow, WorkflowState.FAILED)
                        workflow.updated_at = time.time()
                        self._save_workflow(workflow)

                        self._event_bus.publish(
                            Event(
                                event_type="workflow.failed",
                                data={
                                    "workflow_id": workflow.id,
                                    "stage": stage.name,
                                    "error": str(stage_err),
                                },
                            )
                        )
                        raise WorkflowExecutionError(
                            f"Workflow failed at critical stage '{stage.name}': {stage_err}"
                        ) from stage_err
                    else:
                        logger.warning(
                            f"Optional stage '{stage.name}' failed. Continuing workflow."
                        )
                        workflow.current_stage_index += 1
                        workflow.progress = round(
                            (workflow.current_stage_index / len(workflow.stages))
                            * 100.0,
                            2,
                        )
                        self._save_workflow(workflow)

            WorkflowStateMachine.transition(workflow, WorkflowState.COMPLETED)
            workflow.progress = 100.0
            workflow.updated_at = time.time()
            self._save_workflow(workflow)

            system_settings = self._config.get_system_settings()
            workspace_dir = system_settings.workspace_dir
            report_data = WorkflowReportGenerator.write_reports(workspace_dir, workflow)

            self._event_bus.publish(
                Event(
                    event_type="workflow.completed",
                    data={"workflow_id": workflow.id, "report": report_data},
                )
            )

            return report_data

        except Exception as e:
            if workflow.state != WorkflowState.FAILED:
                WorkflowStateMachine.transition(workflow, WorkflowState.FAILED)
                workflow.updated_at = time.time()
                self._save_workflow(workflow)
            raise e

    def cancel_workflow(self, workflow: Workflow) -> None:
        """Cancels a currently active workflow."""
        WorkflowStateMachine.transition(workflow, WorkflowState.CANCELLED)
        workflow.updated_at = time.time()
        self._save_workflow(workflow)
        logger.info(f"Workflow '{workflow.id}' has been cancelled by user.")

    def _save_workflow(self, workflow: Workflow) -> None:
        """Saves the workflow representation to the persistent key-value store."""
        try:
            workflow_dict = workflow.to_dict()
            self._memory.project.set_metadata(f"workflow:{workflow.id}", workflow_dict)
            self._memory.runtime.set_project_state(
                f"workflow:{workflow.id}", workflow_dict
            )
        except Exception as e:
            logger.error(f"Failed to persist workflow '{workflow.id}' to memory: {e}")

    def load_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Loads a workflow state by ID."""
        try:
            workflow_dict = self._memory.project.get_metadata(f"workflow:{workflow_id}")
            if not workflow_dict:
                workflow_dict = self._memory.runtime.get_project_state(
                    f"workflow:{workflow_id}"
                )
            if not workflow_dict:
                return None

            from .orchestrator import get_interface_map

            return Workflow.from_dict(workflow_dict, get_interface_map())
        except Exception as e:
            logger.error(f"Failed to load workflow '{workflow_id}': {e}")
            return None

    def _bind_stage_action(
        self, workflow: Workflow, stage: WorkflowStage
    ) -> Callable[[], Any]:
        """Binds the workflow stage to its resolved service call."""
        service = self._registry.resolve(stage.service_interface)
        method = getattr(service, stage.method_name)

        def action() -> Any:
            if stage.name == "planner":
                goal = workflow.context.get("goal", "")
                return method(goal)
            elif stage.name == "architect":
                plan = workflow.context.get("project_plan")
                return method(plan)
            elif stage.name == "developer":
                plan = workflow.context.get("project_plan")
                spec = workflow.context.get("architecture_specification")
                return method(plan, spec)
            elif stage.name == "tester":
                plan = workflow.context.get("project_plan")
                spec = workflow.context.get("architecture_specification")
                report = workflow.context.get("implementation_report")
                return method(plan, spec, report)
            elif stage.name == "documentation":
                plan = workflow.context.get("project_plan")
                spec = workflow.context.get("architecture_specification")
                report = workflow.context.get("implementation_report")
                test_report = workflow.context.get("test_report")
                return method(plan, spec, report, test_report)
            elif stage.name == "security":
                plan = workflow.context.get("project_plan")
                spec = workflow.context.get("architecture_specification")
                report = workflow.context.get("implementation_report")
                test_report = workflow.context.get("test_report")
                doc_report = workflow.context.get("documentation_report")
                return method(plan, spec, report, test_report, doc_report)
            elif stage.name == "reviewer":
                plan = workflow.context.get("project_plan")
                spec = workflow.context.get("architecture_specification")
                report = workflow.context.get("implementation_report")
                test_report = workflow.context.get("test_report")
                doc_report = workflow.context.get("documentation_report")
                return method(plan, spec, report, test_report, doc_report)
            elif stage.name == "git":
                plan = workflow.context.get("project_plan")
                spec = workflow.context.get("architecture_specification")
                report = workflow.context.get("implementation_report")
                test_report = workflow.context.get("test_report")
                doc_report = workflow.context.get("documentation_report")
                security_report = workflow.context.get("security_report")
                return method(
                    plan,
                    spec,
                    report,
                    test_report,
                    doc_report,
                    security_report=security_report,
                )
            else:
                return method(**workflow.context)

        return action

    @staticmethod
    def get_default_stages(workflow_type: WorkflowType) -> List[WorkflowStage]:
        """Returns the default stages list for a specific workflow type."""
        from forge_plugins.planner.service import PlannerService
        from forge_plugins.architect.service import ArchitectService
        from forge_plugins.developer.service import DeveloperService
        from forge_plugins.tester.service import TesterService
        from forge_plugins.documentation.service import DocumentationService
        from forge_plugins.security.service import SecurityService
        from forge_plugins.reviewer.service import ReviewerService
        from forge_plugins.git.service import GitService

        stages_dict = {
            "planner": WorkflowStage(
                name="planner",
                service_interface=PlannerService,
                method_name="plan_project",
                retry_count=1,
                retry_delay=2.0,
                timeout=600.0,
                optional=False,
                critical=True,
            ),
            "architect": WorkflowStage(
                name="architect",
                service_interface=ArchitectService,
                method_name="design_architecture",
                retry_count=1,
                retry_delay=2.0,
                timeout=600.0,
                optional=False,
                critical=True,
            ),
            "developer": WorkflowStage(
                name="developer",
                service_interface=DeveloperService,
                method_name="implement_project",
                retry_count=1,
                retry_delay=5.0,
                timeout=900.0,
                optional=False,
                critical=True,
            ),
            "tester": WorkflowStage(
                name="tester",
                service_interface=TesterService,
                method_name="test_project",
                retry_count=1,
                retry_delay=5.0,
                timeout=600.0,
                optional=False,
                critical=True,
            ),
            "documentation": WorkflowStage(
                name="documentation",
                service_interface=DocumentationService,
                method_name="document_project",
                retry_count=1,
                retry_delay=2.0,
                timeout=600.0,
                optional=True,
                critical=False,
            ),
            "security": WorkflowStage(
                name="security",
                service_interface=SecurityService,
                method_name="audit_project",
                retry_count=1,
                retry_delay=2.0,
                timeout=600.0,
                optional=True,
                critical=False,
            ),
            "reviewer": WorkflowStage(
                name="reviewer",
                service_interface=ReviewerService,
                method_name="review_project",
                retry_count=1,
                retry_delay=2.0,
                timeout=600.0,
                optional=True,
                critical=False,
            ),
            "git": WorkflowStage(
                name="git",
                service_interface=GitService,
                method_name="commit_project",
                retry_count=1,
                retry_delay=2.0,
                timeout=300.0,
                optional=True,
                critical=False,
            ),
        }

        if workflow_type == WorkflowType.FULL_ENGINEERING:
            return [
                stages_dict["planner"],
                stages_dict["architect"],
                stages_dict["developer"],
                stages_dict["tester"],
                stages_dict["documentation"],
                stages_dict["security"],
                stages_dict["reviewer"],
                stages_dict["git"],
            ]
        elif workflow_type == WorkflowType.DOCUMENTATION_ONLY:
            return [stages_dict["documentation"]]
        elif workflow_type == WorkflowType.TEST_ONLY:
            return [stages_dict["tester"]]
        elif workflow_type == WorkflowType.BUILD_ONLY:
            return [
                stages_dict["planner"],
                stages_dict["architect"],
                stages_dict["developer"],
            ]
        elif workflow_type == WorkflowType.DELIVERY_ONLY:
            return [stages_dict["git"]]
        else:
            return []

    @staticmethod
    def reconstruct_context(context: Dict[str, Any]) -> Dict[str, Any]:
        """Reconstructs strongly typed models from dictionaries in the context."""
        from unittest.mock import MagicMock

        reconstructed = dict(context)

        # 1. ProjectPlan
        if "project_plan" in reconstructed and isinstance(
            reconstructed["project_plan"], dict
        ):
            if reconstructed["project_plan"].get("__mock__"):
                reconstructed["project_plan"] = MagicMock()
            else:
                from forge_plugins.planner.models import ProjectPlan

                reconstructed["project_plan"] = ProjectPlan.from_dict(
                    reconstructed["project_plan"]
                )

        # 2. ArchitectureSpecification
        if "architecture_specification" in reconstructed and isinstance(
            reconstructed["architecture_specification"], dict
        ):
            if reconstructed["architecture_specification"].get("__mock__"):
                reconstructed["architecture_specification"] = MagicMock()
            else:
                from forge_plugins.architect.models import ArchitectureSpecification

                reconstructed["architecture_specification"] = (
                    ArchitectureSpecification.from_dict(
                        reconstructed["architecture_specification"]
                    )
                )

        # 3. ImplementationReport
        if "implementation_report" in reconstructed and isinstance(
            reconstructed["implementation_report"], dict
        ):
            if reconstructed["implementation_report"].get("__mock__"):
                reconstructed["implementation_report"] = MagicMock()
            else:
                from forge_plugins.developer.models import ImplementationReport

                reconstructed["implementation_report"] = ImplementationReport.from_dict(
                    reconstructed["implementation_report"]
                )

        # 4. TestReport
        if "test_report" in reconstructed and isinstance(
            reconstructed["test_report"], dict
        ):
            if reconstructed["test_report"].get("__mock__"):
                reconstructed["test_report"] = MagicMock()
            else:
                from forge_plugins.tester.models import TestReport

                reconstructed["test_report"] = TestReport.from_dict(
                    reconstructed["test_report"]
                )

        # 5. DocumentationReport
        if "documentation_report" in reconstructed and isinstance(
            reconstructed["documentation_report"], dict
        ):
            if reconstructed["documentation_report"].get("__mock__"):
                reconstructed["documentation_report"] = MagicMock()
            else:
                from forge_plugins.documentation.models import DocumentationReport

                reconstructed["documentation_report"] = DocumentationReport.from_dict(
                    reconstructed["documentation_report"]
                )

        # 6. SecurityReport
        if "security_report" in reconstructed and isinstance(
            reconstructed["security_report"], dict
        ):
            if reconstructed["security_report"].get("__mock__"):
                reconstructed["security_report"] = MagicMock()
            else:
                from forge_plugins.security.models import SecurityReport

                reconstructed["security_report"] = SecurityReport.from_dict(
                    reconstructed["security_report"]
                )

        # 6b. ReviewReport
        if "review_report" in reconstructed and isinstance(
            reconstructed["review_report"], dict
        ):
            if reconstructed["review_report"].get("__mock__"):
                reconstructed["review_report"] = MagicMock()
            else:
                from forge_plugins.reviewer.models import ReviewReport

                reconstructed["review_report"] = ReviewReport.from_dict(
                    reconstructed["review_report"]
                )

        # 7. GitReport
        if "git_report" in reconstructed and isinstance(
            reconstructed["git_report"], dict
        ):
            if reconstructed["git_report"].get("__mock__"):
                reconstructed["git_report"] = MagicMock()
            else:
                from forge_plugins.git.models import GitReport

                reconstructed["git_report"] = GitReport.from_dict(
                    reconstructed["git_report"]
                )

        return reconstructed


def get_interface_map() -> Dict[str, Type[Any]]:
    """Helper to retrieve class references for deserialization."""
    from forge_plugins.planner.service import PlannerService
    from forge_plugins.architect.service import ArchitectService
    from forge_plugins.developer.service import DeveloperService
    from forge_plugins.tester.service import TesterService
    from forge_plugins.documentation.service import DocumentationService
    from forge_plugins.security.service import SecurityService
    from forge_plugins.reviewer.service import ReviewerService
    from forge_plugins.git.service import GitService

    return {
        "PlannerService": PlannerService,
        "ArchitectService": ArchitectService,
        "DeveloperService": DeveloperService,
        "TesterService": TesterService,
        "DocumentationService": DocumentationService,
        "SecurityService": SecurityService,
        "ReviewerService": ReviewerService,
        "GitService": GitService,
    }
