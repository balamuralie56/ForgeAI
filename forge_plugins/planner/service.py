"""
Service definitions and implementation for the ForgeAI Planner Plugin.
"""

import logging
import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.model_router.service import ModelRouterService
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_core.memory.service import MemoryService
from forge_core.task_engine.service import TaskEngineService

from .models import ProjectPlan
from .exceptions import PlanningInferenceError
from .components import (
    RequirementAnalyzer,
    ClarificationEngine,
    TaskDecomposer,
    DependencyBuilder,
    MilestonePlanner,
    WorkflowBuilder,
    RiskAnalyzer,
    PlanningReportGenerator,
)

logger = logging.getLogger("ForgeAI.Plugins.Planner")


class PlannerService(ABC):
    """
    Interface for the Planner service.
    """

    @abstractmethod
    def plan_project(self, goal: str) -> ProjectPlan:
        """
        Decomposes a project goal into a structured ProjectPlan.

        Args:
            goal (str): The project's natural language target description.

        Returns:
            ProjectPlan: The aggregated structural project plan.
        """
        pass


def parse_json_response(text: str) -> Dict[str, Any]:
    """
    Robust JSON parser handling potential markdown and formatting junk in LLM outputs.

    Uses strict=False throughout: general-purpose (non-JSON-mode) local models
    routinely emit literal newlines inside string values - e.g. a
    "directory_structure" field formatted as a human-readable tree - instead of
    escaping them as \\n. Strict JSON parsing rejects raw control characters in
    strings; strict=False allows them, which is exactly what real local-model
    output needs.
    """
    original = text.strip()

    # Attempt 1: parse the whole response directly.
    try:
        return json.loads(original, strict=False)
    except json.JSONDecodeError:
        pass

    # Attempt 2: strip an OUTER markdown fence (```json ... ``` wrapping the
    # entire response). Anchored to start/end so a fence nested inside a JSON
    # string value elsewhere in the response - as in the directory_structure
    # case above - can't be mistaken for the outer wrapper.
    fence_match = re.match(
        r"^```(?:json)?\s*([\s\S]*?)\s*```$", original, flags=re.IGNORECASE
    )
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip(), strict=False)
        except json.JSONDecodeError:
            pass

    # Attempt 3: fall back to the outermost '{' ... '}' span in the ORIGINAL
    # text (never a fence-stripped/corrupted copy of it).
    start = original.find("{")
    end = original.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(original[start : end + 1], strict=False)
        except json.JSONDecodeError as e:
            raise PlanningInferenceError(
                f"Failed to parse LLM response as JSON: {e}. Raw text: {text}"
            ) from e

    raise PlanningInferenceError(
        f"Failed to parse LLM response as JSON: no '{{' ... '}}' object found. Raw text: {text}"
    )


def execute_placeholder_task(task_id: str) -> Dict[str, Any]:
    """Placeholder execution handler for planned tasks."""
    logger.info(f"[Task Execution] Processing placeholder task: {task_id}")
    return {"status": "SUCCESS", "task_id": task_id}


def execute_architecture_task(
    plan_dict: Dict[str, Any], registry: ServiceRegistry
) -> Dict[str, Any]:
    """Automated task trigger to run the Architect design plugin."""
    logger.info("[Task Execution] Automatically triggering Architect service...")
    try:
        # Lazy import and resolve to prevent boot-time dependencies
        from forge_plugins.architect.service import ArchitectService
        from forge_plugins.planner.models import ProjectPlan

        architect = registry.resolve(ArchitectService)  # type: ignore[type-abstract]
        plan = ProjectPlan.from_dict(plan_dict)
        spec = architect.design_architecture(plan)
        return spec.to_dict()
    except Exception as e:
        logger.error(f"[Task Execution] Failed to design software architecture: {e}")
        raise


class ForgeAIPlanner(PlannerService):
    """
    Concrete Planner Service implementation.
    Delegates planning sub-tasks to highly focused internal components.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        """
        Initializes the planner with the system registry and constructs sub-components.

        Args:
            registry (ServiceRegistry): System service container.
        """
        self._registry = registry

        # Construct modular planning sub-components
        self.requirement_analyzer = RequirementAnalyzer(self._model_router)
        self.clarification_engine = ClarificationEngine(self._model_router)
        self.task_decomposer = TaskDecomposer(self._model_router)
        self.dependency_builder = DependencyBuilder(self._model_router)
        self.milestone_planner = MilestonePlanner(self._model_router)
        self.workflow_builder = WorkflowBuilder(self._registry)
        self.risk_analyzer = RiskAnalyzer(self._model_router)
        self.report_generator = PlanningReportGenerator()

    @property
    def _model_router(self) -> ModelRouterService:
        return self._registry.resolve(ModelRouterService)  # type: ignore[type-abstract]

    @property
    def _event_bus(self) -> EventBusService:
        return self._registry.resolve(EventBusService)  # type: ignore[type-abstract]

    @property
    def _memory(self) -> MemoryService:
        return self._registry.resolve(MemoryService)  # type: ignore[type-abstract]

    @property
    def _task_engine(self) -> TaskEngineService:
        return self._registry.resolve(TaskEngineService)  # type: ignore[type-abstract]

    def plan_project(self, goal: str) -> ProjectPlan:
        logger.info(f"Initiating project planning for goal: '{goal}'")

        # 1. Prepare coordinator prompting template
        prompt = f"""You are the Lead Project Planner AI for ForgeAI.
Your task is to analyze the user's project goal and produce a comprehensive, structured project plan.

User Goal:
"{goal}"

You must output a single valid JSON object containing the project plan. Do not include any explanation outside the JSON.
The JSON must adhere to the following schema:
{{
    "goal": {{
        "goal": "Brief title of the goal",
        "description": "Elaborate description of the goal"
    }},
    "requirements": [
        {{
            "requirement_id": "REQ-001",
            "description": "Requirement description",
            "is_functional": true,
            "priority": "HIGH",
            "dependencies": []
        }}
    ],
    "clarifications": [
        {{
            "question_id": "Q-001",
            "question": "Clarifying question",
            "context": "Context on why this is needed",
            "assumed_answer": "Reasonable default answer/assumption"
        }}
    ],
    "milestones": [
        {{
            "milestone_id": "M-001",
            "title": "Milestone Title",
            "description": "Milestone Description",
            "tasks": ["TASK-001"]
        }}
    ],
    "tasks": [
        {{
            "task_id": "TASK-001",
            "name": "Task Name",
            "description": "Task Description",
            "milestone_id": "M-001",
            "dependencies": [],
            "estimated_duration_hours": 2.0
        }}
    ],
    "dependencies": [
        {{
            "task_id": "TASK-001",
            "depends_on_task_id": "TASK-000",
            "dependency_type": "finish_to_start"
        }}
    ],
    "estimated_order": ["TASK-001"],
    "risks": [
        "Risk description"
    ],
    "assumptions": [
        "Assumption description"
    ]
}}
"""

        # 2. Call LLM Router for centralized plan synthesis
        try:
            response = self._model_router.generate(prompt)
            raw_text = response.text
        except Exception as e:
            raise PlanningInferenceError(f"Model Router generation failed: {e}") from e

        # 3. Resilient JSON Parse
        plan_data = parse_json_response(raw_text)

        # 4. Delegate to specialized sub-components to construct dataclasses
        try:
            from .models import ProjectGoal

            goal_data = plan_data.get("goal") or {}
            project_goal = ProjectGoal.from_dict(goal_data)

            requirements = self.requirement_analyzer.extract_from_data(plan_data)
            clarifications = self.clarification_engine.extract_from_data(plan_data)
            tasks = self.task_decomposer.extract_from_data(plan_data)
            dependencies = self.dependency_builder.extract_from_data(plan_data)
            milestones = self.milestone_planner.extract_from_data(plan_data)
            risks = self.risk_analyzer.extract_risks(plan_data)
            assumptions = self.risk_analyzer.extract_assumptions(plan_data)
            estimated_order = plan_data.get("estimated_order") or []

            plan = ProjectPlan(
                goal=project_goal,
                requirements=requirements,
                clarifications=clarifications,
                milestones=milestones,
                tasks=tasks,
                dependencies=dependencies,
                estimated_order=estimated_order,
                risks=risks,
                assumptions=assumptions,
            )
        except Exception as e:
            raise PlanningInferenceError(f"Failed to map plan data: {e}") from e

        # 5. Persist to memory
        plan_dict = plan.to_dict()
        self._memory.runtime.set_project_state("project_plan", plan_dict)
        self._memory.project.set_metadata("project_plan", plan_dict)

        # 6. Publish Event
        event = Event(event_type="planner.plan_created", data=plan_dict)
        self._event_bus.publish(event)

        # 7. Convert planning tasks into a TaskDAG and submit to TaskEngine via WorkflowBuilder
        logger.info("Constructing TaskDAG pipeline from ProjectPlan...")
        dag = self.workflow_builder.build_workflow(plan)
        run_id = self._task_engine.submit_dag(dag)
        logger.info(f"TaskDAG successfully registered under run ID: '{run_id}'")

        logger.info("Project planning completed successfully.")
        return plan
