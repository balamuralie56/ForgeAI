"""
Unit tests for the Architect plugin.
Verifies software architecture specification modeling, technology decisions, ADRs, database design, and events mapping.
"""

import unittest
from unittest.mock import MagicMock

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.model_router.service import ModelRouterService, ModelResponse
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_core.memory.service import MemoryService, ForgeAIMemoryService

from forge_plugins.planner.models import ProjectPlan, ProjectGoal
from forge_plugins.architect.service import ForgeAIArchitect
from forge_plugins.architect.exceptions import ArchitectureInferenceError


class TestArchitectPlugin(unittest.TestCase):
    """Test suite for the Architect Service."""

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

        self.architect = ForgeAIArchitect(self.registry)

    def tearDown(self) -> None:
        """Cleanup memory engine."""
        self.memory.shutdown()

    def test_design_architecture_success(self) -> None:
        """Verifies successful architecture spec design and serialization mapping."""
        plan = ProjectPlan(goal=ProjectGoal(goal="Test", description="Desc"))

        mock_spec_json = """
        {
            "project_id": "test-project-123",
            "directory_structure": "src/\\n  main.py",
            "modules": [
                {
                    "name": "core",
                    "purpose": "Business logic boundaries",
                    "dependencies": [],
                    "apis": [
                        {
                            "path": "/api/run",
                            "method": "POST",
                            "description": "Trigger run",
                            "request_payload_schema": "JSON Schema",
                            "response_payload_schema": "JSON Schema"
                        }
                    ]
                }
            ],
            "database_design": [
                {
                    "table_name": "users",
                    "columns": {
                        "id": "INTEGER PRIMARY KEY"
                    },
                    "primary_key": "id",
                    "foreign_keys": {},
                    "description": "Storage for user profiles"
                }
            ],
            "decisions": [
                {
                    "category": "Backend",
                    "technology": "FastAPI",
                    "rationale": "Fast performance and automated docs"
                }
            ],
            "adrs": [
                {
                    "adr_id": "ADR-001",
                    "title": "Adopt FastAPI",
                    "status": "Accepted",
                    "context": "Need clean REST framework",
                    "decision": "Use FastAPI",
                    "consequences": "Automatic interactive OpenAPI documentation",
                    "date": "2026-07-04"
                }
            ],
            "mermaid_diagrams": {
                "context": "graph TD\\n  A --> B"
            },
            "rationale": "System design rationale"
        }
        """

        self.mock_router.generate.return_value = ModelResponse(
            text=mock_spec_json, raw_response={}, model_name="mock-model"
        )

        spec = self.architect.design_architecture(plan)

        # 1. Assert spec data properties
        self.assertEqual(spec.project_id, "test-project-123")
        self.assertEqual(len(spec.modules), 1)
        self.assertEqual(spec.modules[0].name, "core")
        self.assertEqual(len(spec.database_design), 1)
        self.assertEqual(spec.database_design[0].table_name, "users")
        self.assertEqual(len(spec.adrs), 1)
        self.assertEqual(spec.adrs[0].adr_id, "ADR-001")

        # 2. Assert memory persistence
        memory_spec_dict = self.memory.runtime.get_project_state(
            "architecture_specification"
        )
        self.assertIsNotNone(memory_spec_dict)
        self.assertEqual(memory_spec_dict["project_id"], "test-project-123")

        # 3. Assert Event Bus dispatch
        self.mock_event_bus.publish.assert_called_once()
        published_event = self.mock_event_bus.publish.call_args[0][0]
        self.assertIsInstance(published_event, Event)
        self.assertEqual(published_event.event_type, "architect.spec_created")
        self.assertEqual(published_event.data["project_id"], "test-project-123")

        # 4. Assert architecture history entry
        history = self.memory.project.get_architecture_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["entry"]["project_id"], "test-project-123")

    def test_design_architecture_inference_failure(self) -> None:
        """Verifies that non-JSON outputs raise ArchitectureInferenceError."""
        plan = ProjectPlan(goal=ProjectGoal(goal="Test", description="Desc"))

        self.mock_router.generate.return_value = ModelResponse(
            text="Invalid output text string", raw_response={}, model_name="mock-model"
        )

        with self.assertRaises(ArchitectureInferenceError):
            self.architect.design_architecture(plan)


if __name__ == "__main__":
    unittest.main()
