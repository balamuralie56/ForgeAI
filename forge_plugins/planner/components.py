"""
Modular sub-components for the ForgeAI Planner Plugin.
"""

import logging
from typing import Any, Dict, List
from forge_core.model_router.service import ModelRouterService
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.task_engine.models import Task as EngineTask
from forge_core.task_engine.dag import TaskDAG

from .models import (
    Requirement,
    ClarificationQuestion,
    Milestone,
    Task,
    TaskDependency,
    ProjectPlan,
)

logger = logging.getLogger("ForgeAI.Plugins.Planner.Components")


class RequirementAnalyzer:
    """Requirement Analyzer component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def extract_from_data(self, data: Dict[str, Any]) -> List[Requirement]:
        reqs_data = data.get("requirements") or []
        return [Requirement.from_dict(req) for req in reqs_data]

    def analyze(self, goal: str) -> List[Requirement]:
        logger.info(f"RequirementAnalyzer analyzing requirements for: '{goal}'")
        # Support independent prompt if executed standalone
        return []


class ClarificationEngine:
    """Clarification Engine component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def extract_from_data(self, data: Dict[str, Any]) -> List[ClarificationQuestion]:
        clar_data = data.get("clarifications") or []
        return [ClarificationQuestion.from_dict(c) for c in clar_data]

    def clarify(self, goal: str) -> List[ClarificationQuestion]:
        logger.info(f"ClarificationEngine analyzing clarifications for: '{goal}'")
        return []


class TaskDecomposer:
    """Task Decomposer component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def extract_from_data(self, data: Dict[str, Any]) -> List[Task]:
        tasks_data = data.get("tasks") or []
        return [Task.from_dict(t) for t in tasks_data]

    def decompose(self, goal: str) -> List[Task]:
        logger.info(f"TaskDecomposer decomposing goal: '{goal}'")
        return []


class DependencyBuilder:
    """Dependency Builder component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def extract_from_data(self, data: Dict[str, Any]) -> List[TaskDependency]:
        deps_data = data.get("dependencies") or []
        return [TaskDependency.from_dict(d) for d in deps_data]

    def build_dependencies(self, tasks: List[Task]) -> List[TaskDependency]:
        logger.info("DependencyBuilder building task dependency chains")
        return []


class MilestonePlanner:
    """Milestone Planner component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def extract_from_data(self, data: Dict[str, Any]) -> List[Milestone]:
        miles_data = data.get("milestones") or []
        return [Milestone.from_dict(m) for m in miles_data]

    def plan_milestones(self, tasks: List[Task]) -> List[Milestone]:
        logger.info("MilestonePlanner planning development milestones")
        return []


class WorkflowBuilder:
    """Workflow Builder component."""

    def __init__(self, registry: ServiceRegistry) -> None:
        self._registry = registry

    def build_workflow(self, plan: ProjectPlan) -> TaskDAG:
        logger.info("WorkflowBuilder constructing execution TaskDAG pipeline")

        # Lazy imports and resolutions
        from forge_plugins.planner.service import (
            execute_architecture_task,
            execute_placeholder_task,
        )

        engine_tasks: List[EngineTask] = []
        plan_dict = plan.to_dict()
        for task in plan.tasks:
            task_deps = task.dependencies

            if task.task_id == "TASK-001" or (len(engine_tasks) == 0 and not task_deps):

                def make_arch_callable(
                    p_dict: Dict[str, Any], reg: ServiceRegistry
                ) -> Any:
                    def _run(task_obj: Any = None) -> Any:
                        return execute_architecture_task(p_dict, reg)

                    return _run

                callable_wrapper = make_arch_callable(plan_dict, self._registry)
            else:

                def make_placeholder_callable(t_id: str) -> Any:
                    def _run(task_obj: Any = None) -> Any:
                        return execute_placeholder_task(t_id)

                    return _run

                callable_wrapper = make_placeholder_callable(task.task_id)

            engine_task = EngineTask(
                task_id=task.task_id,
                name=task.name,
                execution_callable=callable_wrapper,
                dependencies=task_deps,
                metadata={"milestone_id": task.milestone_id},
            )
            engine_tasks.append(engine_task)

        return TaskDAG(engine_tasks)


class RiskAnalyzer:
    """Risk Analyzer component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def extract_risks(self, data: Dict[str, Any]) -> List[str]:
        return data.get("risks") or []

    def extract_assumptions(self, data: Dict[str, Any]) -> List[str]:
        return data.get("assumptions") or []

    def analyze_risks(self, goal: str) -> Dict[str, List[str]]:
        logger.info(f"RiskAnalyzer analyzing risks for: '{goal}'")
        return {"risks": [], "assumptions": []}


class PlanningReportGenerator:
    """Planning Report Generator component."""

    def generate_report(self, plan: ProjectPlan) -> str:
        logger.info(
            f"PlanningReportGenerator generating project plan report for: '{plan.goal.goal}'"
        )
        return f"# Planning Report - {plan.goal.goal}\n\n{plan.goal.description}"
