"""
Service interface and concrete implementation for the ForgeAI Workflow Orchestrator.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.kernel.lifecycle import LifecycleComponent
from .models import Workflow, WorkflowStage, WorkflowType
from .orchestrator import WorkflowOrchestrator

logger = logging.getLogger("ForgeAI.Workflow.Service")


class WorkflowService(ABC):
    """
    Interface for the Workflow Orchestrator service.
    """

    @abstractmethod
    def create_workflow(
        self,
        workflow_type: WorkflowType,
        name: str,
        goal: str,
        custom_stages: Optional[List[WorkflowStage]] = None,
    ) -> Workflow:
        """
        Creates a new workflow configuration.
        """
        pass

    @abstractmethod
    def run_workflow(self, workflow: Workflow) -> Dict[str, Any]:
        """
        Runs the specified workflow configuration.
        """
        pass

    @abstractmethod
    def cancel_workflow(self, workflow: Workflow) -> None:
        """
        Cancels the running workflow.
        """
        pass

    @abstractmethod
    def load_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """
        Loads a workflow by its unique ID.
        """
        pass


class ForgeAIWorkflowService(WorkflowService, LifecycleComponent):
    """
    Concrete Workflow Service implementation tied to the Kernel lifecycle.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        """
        Initializes the service with dependency registry.
        """
        self._registry = registry
        self._orchestrator: Optional[WorkflowOrchestrator] = None

    def initialize(self) -> None:
        """Lifecycle hook to boot the service."""
        self._orchestrator = WorkflowOrchestrator(self._registry)
        logger.info("Workflow service initialized successfully.")

    def shutdown(self) -> None:
        """Lifecycle hook to shutdown the service."""
        logger.info("Workflow service shut down.")

    def create_workflow(
        self,
        workflow_type: WorkflowType,
        name: str,
        goal: str,
        custom_stages: Optional[List[WorkflowStage]] = None,
    ) -> Workflow:
        if not self._orchestrator:
            raise RuntimeError("Workflow service is not initialized.")
        return self._orchestrator.create_workflow(
            workflow_type=workflow_type,
            name=name,
            goal=goal,
            custom_stages=custom_stages,
        )

    def run_workflow(self, workflow: Workflow) -> Dict[str, Any]:
        if not self._orchestrator:
            raise RuntimeError("Workflow service is not initialized.")
        return self._orchestrator.run_workflow(workflow)

    def cancel_workflow(self, workflow: Workflow) -> None:
        if not self._orchestrator:
            raise RuntimeError("Workflow service is not initialized.")
        self._orchestrator.cancel_workflow(workflow)

    def load_workflow(self, workflow_id: str) -> Optional[Workflow]:
        if not self._orchestrator:
            raise RuntimeError("Workflow service is not initialized.")
        return self._orchestrator.load_workflow(workflow_id)
