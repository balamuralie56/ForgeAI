"""
Unit tests for the Planner plugin.
Verifies LLM generation parsing, structured ProjectPlan mapping, Event Bus publishing, and Task Engine submissions.
"""

import unittest
from unittest.mock import MagicMock

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.model_router.service import ModelRouterService, ModelResponse
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_core.memory.service import MemoryService, ForgeAIMemoryService
from forge_core.task_engine.service import TaskEngineService
from forge_core.task_engine.task_engine import ForgeAITaskEngine

from forge_plugins.planner.service import ForgeAIPlanner, parse_json_response
from forge_plugins.planner.exceptions import PlanningInferenceError


class TestPlannerPlugin(unittest.TestCase):
    """Test suite for the Planner Service."""

    def setUp(self) -> None:
        """Setup registry and mocks."""
        self.registry = ServiceRegistry()

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

        # 4. Setup Task Engine
        self.task_engine = ForgeAITaskEngine(self.mock_event_bus, self.memory)
        self.task_engine.initialize()
        self.registry.register(TaskEngineService, self.task_engine)  # type: ignore[type-abstract]

        self.planner = ForgeAIPlanner(self.registry)

    def tearDown(self) -> None:
        """Cleanup memory and task engines."""
        self.task_engine.shutdown()
        self.memory.shutdown()

    def test_plan_project_success(self) -> None:
        """Verifies successful LLM parsing and engine side-effects."""
        mock_response_json = """
        {
            "goal": {
                "goal": "Test Project",
                "description": "Goal description"
            },
            "requirements": [
                {
                    "requirement_id": "REQ-1",
                    "description": "Functional spec",
                    "is_functional": true,
                    "priority": "HIGH",
                    "dependencies": []
                }
            ],
            "clarifications": [
                {
                    "question_id": "Q-1",
                    "question": "What model?",
                    "context": "Context on models",
                    "assumed_answer": "Local deepseek"
                }
            ],
            "milestones": [
                {
                    "milestone_id": "M-1",
                    "title": "Milestone title",
                    "description": "Milestone desc",
                    "tasks": ["TASK-001"]
                }
            ],
            "tasks": [
                {
                    "task_id": "TASK-001",
                    "name": "Design Spec",
                    "description": "Design spec task",
                    "milestone_id": "M-1",
                    "dependencies": [],
                    "estimated_duration_hours": 2.0
                }
            ],
            "dependencies": [],
            "estimated_order": ["TASK-001"],
            "risks": ["Risk details"],
            "assumptions": ["Assumption details"]
        }
        """
        self.mock_router.generate.return_value = ModelResponse(
            text=mock_response_json, raw_response={}, model_name="mock-model"
        )

        plan = self.planner.plan_project("Build a test app")

        # 1. Assert plan data mapping
        self.assertEqual(plan.goal.goal, "Test Project")
        self.assertEqual(len(plan.requirements), 1)
        self.assertEqual(plan.requirements[0].requirement_id, "REQ-1")
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(plan.tasks[0].task_id, "TASK-001")

        # 2. Assert memory persistence
        memory_plan_dict = self.memory.runtime.get_project_state("project_plan")
        self.assertIsNotNone(memory_plan_dict)
        self.assertEqual(memory_plan_dict["goal"]["goal"], "Test Project")

        # 3. Assert Event Bus dispatch
        self.mock_event_bus.publish.assert_called_once()
        published_event = self.mock_event_bus.publish.call_args[0][0]
        self.assertIsInstance(published_event, Event)
        self.assertEqual(published_event.event_type, "planner.plan_created")
        self.assertEqual(published_event.data["goal"]["goal"], "Test Project")

        # 4. Assert Task Engine Submission
        dag_status = self.memory.runtime.get_execution_state(
            "dag:" + list(self.task_engine._dag_runs.keys())[0] + ":status"
        )
        self.assertEqual(dag_status, "SUBMITTED")

    def test_plan_project_inference_failure(self) -> None:
        """Verifies that non-JSON output throws PlanningInferenceError."""
        self.mock_router.generate.return_value = ModelResponse(
            text="This is not valid JSON string",
            raw_response={},
            model_name="mock-model",
        )

        with self.assertRaises(PlanningInferenceError):
            self.planner.plan_project("Build a test app")


class TestParseJsonResponse(unittest.TestCase):
    """
    Direct tests for parse_json_response - previously had zero coverage of its
    own, which is exactly how the bugs below survived: mocked model responses
    in the service-level tests are always clean, valid JSON and never exercise
    the messy-real-LLM-output paths.
    """

    def test_clean_json(self) -> None:
        result = parse_json_response('{"a": 1, "b": "two"}')
        self.assertEqual(result, {"a": 1, "b": "two"})

    def test_json_wrapped_in_outer_markdown_fence(self) -> None:
        text = '```json\n{"a": 1}\n```'
        self.assertEqual(parse_json_response(text), {"a": 1})

    def test_json_with_raw_newline_inside_string_value(self) -> None:
        """
        Real failure mode: general-purpose local models routinely emit a
        literal newline inside a string value (e.g. formatting a directory
        tree "nicely") instead of escaping it as \\n. Strict JSON parsing
        rejects this; parse_json_response must not.
        """
        text = '{\n  "tree": "root\nchild"\n}'
        result = parse_json_response(text)
        self.assertEqual(result["tree"], "root\nchild")

    def test_json_with_fence_nested_inside_a_string_value(self) -> None:
        """
        Regression test for a real bug hit via a live end-to-end run: when a
        JSON string value itself contains a ```fenced``` block (e.g. a
        directory_structure field formatted as a markdown tree), the outer-
        fence-stripping regex must not mistake that nested fence for the
        response's own wrapper - and if it does, the final '{'...'}' fallback
        must still search the ORIGINAL text, not a copy already corrupted by
        that mismatch.
        """
        text = (
            "{\n"
            '  "project_id": "PROJ-001",\n'
            '  "directory_structure": "```markdown\n'
            "root/\n"
            "  file.py\n"
            '```",\n'
            '  "modules": []\n'
            "}"
        )
        result = parse_json_response(text)
        self.assertEqual(result["project_id"], "PROJ-001")
        self.assertEqual(result["modules"], [])
        self.assertIn("root/", result["directory_structure"])

    def test_json_embedded_in_surrounding_prose(self) -> None:
        text = 'Sure, here is the plan:\n{"a": 1}\nHope that helps!'
        self.assertEqual(parse_json_response(text), {"a": 1})

    def test_unparseable_text_raises(self) -> None:
        with self.assertRaises(PlanningInferenceError):
            parse_json_response("This is not valid JSON string")


if __name__ == "__main__":
    unittest.main()
