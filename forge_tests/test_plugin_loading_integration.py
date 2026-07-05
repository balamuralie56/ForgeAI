"""
Integration tests for the Planner and Architect plugins.
Verifies dynamic plugin package discovery/loading and end-to-end execution flow through the Task Engine.
"""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from forge_core.kernel.kernel import ForgeAIKernel
from forge_core.model_router.service import ModelRouterService, ModelResponse
from forge_core.memory.service import MemoryService
from forge_core.task_engine.service import TaskEngineService

from forge_plugins.planner.service import PlannerService
from forge_plugins.architect.service import ArchitectService


class TestPluginLoadingIntegration(unittest.TestCase):
    """Integration test suite for dynamic loading and service execution."""

    def setUp(self) -> None:
        """Setup custom configuration to trigger plugin discovery."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.temp_dir.name) / "config"
        self.config_dir.mkdir()

        # Generate default config enabling planner and architect plugins
        defaults_file = self.config_dir / "defaults.json"
        defaults_file.write_text(
            """
        {
            "version": "1.0",
            "schema_version": "1.0",
            "system": {
                "workspace_dir": "test_workspace",
                "log_dir": "test_logs",
                "log_level": "INFO"
            },
            "models": {
                "provider": "ollama",
                "default_model": "qwen2.5-coder:7b",
                "base_url": "http://localhost:11434",
                "temperature": 0.7,
                "max_tokens": 8192
            },
            "plugins": {
                "plugin_dir": "forge_plugins",
                "enabled_plugins": ["planner", "architect"]
            }
        }
        """,
            encoding="utf-8",
        )

        self.kernel = ForgeAIKernel(
            config_path=str(Path(self.temp_dir.name) / "forge.json"),
            defaults_path=str(defaults_file),
        )

    def tearDown(self) -> None:
        """Tears down the kernel and removes config directory."""
        if self.kernel._booted:
            self.kernel.shutdown()
        self.temp_dir.cleanup()

    def test_dynamic_plugin_loading_and_e2e_execution(self) -> None:
        """Verifies plugins load and collaborate via the Task Engine execution loop."""
        self.kernel.boot()
        self.assertTrue(self.kernel._booted)

        # 1. Resolve registered services
        planner = self.kernel.registry.resolve(PlannerService)  # type: ignore[type-abstract]
        architect = self.kernel.registry.resolve(ArchitectService)  # type: ignore[type-abstract]

        self.assertIsNotNone(planner)
        self.assertIsNotNone(architect)

        # 2. Mock LLM responses for both planning and architecture specifications
        mock_plan_json = """
        {
            "goal": {
                "goal": "Integration App",
                "description": "Integration goal"
            },
            "requirements": [
                {
                    "requirement_id": "REQ-1",
                    "description": "Functional description",
                    "is_functional": true,
                    "priority": "HIGH",
                    "dependencies": []
                }
            ],
            "clarifications": [],
            "milestones": [
                {
                    "milestone_id": "M-1",
                    "title": "Milestone title",
                    "description": "Milestone description",
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
            "risks": [],
            "assumptions": []
        }
        """

        mock_spec_json = """
        {
            "project_id": "integration-project-123",
            "directory_structure": "src/\\n  main.py",
            "modules": [
                {
                    "name": "core",
                    "purpose": "Decoupled logic",
                    "dependencies": [],
                    "apis": []
                }
            ],
            "database_design": [],
            "decisions": [],
            "adrs": [
                {
                    "adr_id": "ADR-001",
                    "title": "Adopt Python",
                    "status": "Accepted",
                    "context": "Need simple typing",
                    "decision": "Use Python",
                    "consequences": "Dynamic execution",
                    "date": "2026-07-04"
                }
            ],
            "mermaid_diagrams": {},
            "rationale": "Rationale details"
        }
        """

        # Intercept Model Router generate method to yield mock JSON outputs
        router = self.kernel.registry.resolve(ModelRouterService)  # type: ignore[type-abstract]
        mock_generate = MagicMock()
        mock_generate.side_effect = [
            ModelResponse(text=mock_plan_json, raw_response={}, model_name="mock-m"),
            ModelResponse(text=mock_spec_json, raw_response={}, model_name="mock-m"),
        ]
        router.generate = mock_generate  # type: ignore[method-assign]

        # 3. Trigger project planning
        plan = planner.plan_project("Build integration app")
        self.assertEqual(plan.goal.goal, "Integration App")

        # 4. Resolve task engine and execute the generated DAG pipeline
        task_engine = self.kernel.registry.resolve(TaskEngineService)  # type: ignore[type-abstract]
        run_ids = list(task_engine._dag_runs.keys())  # type: ignore[attr-defined]
        self.assertEqual(len(run_ids), 1)
        run_id = run_ids[0]

        # Execute DAG which includes the architecture task callable
        results = asyncio.run(task_engine.execute_dag(run_id))
        self.assertIn("TASK-001", results)

        # 5. Confirm that the architecture task triggered the Architect Plugin
        # and saved the ArchitectureSpecification to project memory
        memory = self.kernel.registry.resolve(MemoryService)  # type: ignore[type-abstract]
        spec_dict = memory.runtime.get_project_state("architecture_specification")

        self.assertIsNotNone(spec_dict)
        self.assertEqual(spec_dict["project_id"], "integration-project-123")
        self.assertEqual(spec_dict["adrs"][0]["title"], "Adopt Python")


if __name__ == "__main__":
    unittest.main()
