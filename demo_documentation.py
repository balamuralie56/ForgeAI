"""
End-to-end demo: Documentation Plugin (runnable from ForgeAI root).
"""
import json
import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.model_router.service import ModelRouterService, ModelResponse
from forge_core.event_bus.service import EventBusService
from forge_core.memory.service import MemoryService, ForgeAIMemoryService
from forge_core.configuration.service import ConfigurationService
from forge_core.configuration.models import (
    ForgeConfig, SystemSettings, ModelSettings, PluginSettings,
)
from forge_plugins.planner.models import ProjectPlan, ProjectGoal
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport, GeneratedFile
from forge_plugins.tester.models import TestReport, GeneratedTestFile
from forge_plugins.documentation.service import ForgeAIDocumentation

logging.basicConfig(level=logging.WARNING)


def make_resp(category: str, n: int = 2) -> ModelResponse:
    files = [
        {"path": f"docs/{category}_{i}.md", "content": f"# {category} doc {i}", "category": category}
        for i in range(1, n + 1)
    ]
    return ModelResponse(text=json.dumps({"files": files}), raw_response={}, model_name="mock")


def main() -> None:
    with tempfile.TemporaryDirectory() as ws:
        registry = ServiceRegistry()
        mock_router = MagicMock(spec=ModelRouterService)
        mock_event_bus = MagicMock(spec=EventBusService)
        mock_config = MagicMock(spec=ConfigurationService)

        sys_settings = SystemSettings(workspace_dir=ws, log_level="INFO")
        full_config = ForgeConfig(
            version="1.0", schema_version="1.0", system=sys_settings,
            models=ModelSettings(
                provider="ollama", default_model="qwen2.5-coder:7b",
                base_url="http://localhost:11434", temperature=0.7, max_tokens=8192,
            ),
            plugins=PluginSettings(),
        )
        mock_config.get_system_settings.return_value = sys_settings
        mock_config.get_full_config.return_value = full_config

        memory = ForgeAIMemoryService(db_path=":memory:")
        memory.initialize()

        registry.register(ModelRouterService, mock_router)   # type: ignore[type-abstract]
        registry.register(EventBusService, mock_event_bus)   # type: ignore[type-abstract]
        registry.register(MemoryService, memory)             # type: ignore[type-abstract]
        registry.register(ConfigurationService, mock_config) # type: ignore[type-abstract]

        # 6 generator responses + summary step (no LLM call)
        mock_router.generate.side_effect = [
            make_resp("project", 5),
            make_resp("developer", 3),
            make_resp("api", 2),
            make_resp("architecture", 1),
            make_resp("user", 3),
            make_resp("release", 1),
        ]

        plan = ProjectPlan(
            goal=ProjectGoal(goal="FastAPI Todo API", description="REST API"),
            requirements=[], clarifications=[], milestones=[], tasks=[], estimated_order=[],
        )
        spec = ArchitectureSpecification(
            project_id="todo-api-v1", directory_structure="src/",
            modules=[], database_design=[], decisions=[], adrs=[],
        )
        report = ImplementationReport(
            project_id="todo-api-v1",
            files=[GeneratedFile(path="src/main.py", content="from fastapi import FastAPI", file_type="backend")],
            status="SUCCESS", summary="",
        )
        test_report = TestReport(
            project_id="todo-api-v1",
            test_files=[GeneratedTestFile(path="tests/test_api.py", content="def test_ok(): pass", test_type="unit")],
            status="SUCCESS", summary="",
        )

        svc = ForgeAIDocumentation(registry)
        doc = svc.document_project(plan, spec, report, test_report)

        print("=" * 65)
        print("  ForgeAI Documentation Plugin — Demo Results")
        print("=" * 65)
        print(f"  Status          : {doc.status}")
        print(f"  Project ID      : {doc.project_id}")
        print(f"  Files generated : {len(doc.doc_files)}")
        print()
        col_path = "Path"
        col_cat  = "Category"
        col_size = "Size"
        print(f"  {col_path:<44} {col_cat:<14} {col_size}")
        print("  " + "-" * 70)
        for df in doc.doc_files:
            size = len(df.content.encode("utf-8"))
            print(f"  {df.path:<44} {df.category:<14} {size} bytes")

        manifest_path = Path(ws) / "docs_manifest.json"
        if manifest_path.exists():
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            print(f"\n  docs_manifest.json  =>  {m['generated_documents']} documents registered.")
        index_path = Path(ws) / "docs" / "INDEX.md"
        if index_path.exists():
            print(f"  docs/INDEX.md       =>  {index_path.stat().st_size} bytes.")
        print("\n  Demo PASSED ✓")
        print("=" * 65)


if __name__ == "__main__":
    main()
