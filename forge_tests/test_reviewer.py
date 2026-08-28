"""
Unit and integration tests for the ForgeAI Reviewer Plugin.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

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
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding, ReviewReport, ReviewManifest
from forge_plugins.reviewer.exceptions import (
    ReviewerValidationError,
    ReviewerError,
)
from forge_plugins.reviewer.service import ForgeAIReviewer
from forge_plugins.reviewer.plugin import ReviewerPlugin
from forge_plugins.reviewer.validators.reviewer_validator import ReviewerValidator
from forge_plugins.reviewer.components.static_analyzer import ReviewStaticAnalyzer
from forge_plugins.reviewer.components.solid_scorer import SolidScorer
from forge_plugins.reviewer.components.report_generator import ReviewReportGenerator
from forge_plugins.reviewer.writers.reviewer_writer import ReviewerWorkspaceWriter
from forge_plugins.security.components.ignore_engine import SecurityIgnoreEngine

DEFAULT_RULES = {
    "REV-001-LONGFUNC": True,
    "REV-002-TOOMANYPARAMS": True,
    "REV-003-GODCLASS": True,
    "REV-004-DEEPNESTING": True,
    "REV-005-MAGICNUMBER": True,
    "REV-006-NODOCSTRING": True,
    "REV-007-MUTABLEDEFAULT": True,
    "REV-008-TYPECHECKCHAIN": True,
    "REV-009-FATINTERFACE": True,
    "REV-010-CONCRETEDEP": True,
}


class TestReviewerPlugin(unittest.TestCase):
    """Test suite covering rule checks, components, the pipeline, gates, and E2E runs."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_path = self.temp_dir.name

        self.mock_router = MagicMock(spec=ModelRouterService)
        mock_response = MagicMock(spec=ModelResponse)
        mock_response.text = "AI Review: extract the nested block into a helper."
        self.mock_router.generate.return_value = mock_response

        self.mock_config = MagicMock(spec=ConfigurationService)
        self.sys_settings = SystemSettings(
            workspace_dir=self.workspace_path, log_level="INFO"
        )
        self.mock_config.get_system_settings.return_value = self.sys_settings

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
            reviewer={
                "enabled": True,
                "llm_review": True,
                "block_release": False,
                "min_quality_score": 50.0,
                "rules": dict(DEFAULT_RULES),
            },
        )
        self.mock_config.get_full_config.return_value = self.full_config

        self.registry = ServiceRegistry()
        self.registry.register(ModelRouterService, self.mock_router)  # type: ignore[type-abstract]
        self.registry.register(ConfigurationService, self.mock_config)  # type: ignore[type-abstract]

        self.event_bus_mock = MagicMock(spec=EventBusService)
        self.registry.register(EventBusService, self.event_bus_mock)  # type: ignore[type-abstract]

        self.memory = ForgeAIMemoryService(db_path=":memory:")
        self.memory.initialize()
        self.registry.register(MemoryService, self.memory)  # type: ignore[type-abstract]

        self.reviewer_service = ForgeAIReviewer(self.registry)
        self.reviewer_service.initialize()

    def tearDown(self) -> None:
        self.reviewer_service.shutdown()
        self.memory.shutdown()
        self.temp_dir.cleanup()

    def _write(self, name: str, code: str) -> Path:
        path = Path(self.workspace_path) / name
        path.write_text(code, encoding="utf-8")
        return path

    def _make_mock_artifacts(self):
        plan = ProjectPlan(
            goal=ProjectGoal(goal="Todo app", description="Task manager"),
            requirements=[],
            clarifications=[],
            milestones=[],
            tasks=[],
            estimated_order=[],
        )
        spec = ArchitectureSpecification(
            project_id="test_proj",
            directory_structure="app.py",
            modules=[],
            database_design=[],
            decisions=[],
            adrs=[],
        )
        report = ImplementationReport(
            project_id="test_proj",
            files=[GeneratedFile(path="app.py", content="", file_type="backend")],
            status="SUCCESS",
            summary="",
        )
        return plan, spec, report

    def _scan(self, rules=None):
        ignore = SecurityIgnoreEngine(self.workspace_path)
        analyzer = ReviewStaticAnalyzer(self.workspace_path, ignore)
        return analyzer.scan_files(rules or DEFAULT_RULES)

    # ─── Individual Rule Checks ──────────────────────────────────────────────

    def test_long_function_rule(self) -> None:
        body = "\n".join(f"    x{i} = {i}" for i in range(60))
        self._write("long.py", f"def big():\n{body}\n    return x0\n")
        findings = self._scan()
        self.assertIn("REV-001-LONGFUNC", [f.rule_id for f in findings])

    def test_long_function_rule_ok_when_short(self) -> None:
        self._write("short.py", "def small():\n    return 1\n")
        findings = self._scan()
        self.assertNotIn("REV-001-LONGFUNC", [f.rule_id for f in findings])

    def test_too_many_parameters_rule(self) -> None:
        self._write("params.py", "def f(a, b, c, d, e, f):\n    return a\n")
        findings = self._scan()
        self.assertIn("REV-002-TOOMANYPARAMS", [f.rule_id for f in findings])

    def test_too_many_parameters_ignores_self(self) -> None:
        self._write(
            "params_ok.py",
            "class C:\n    def m(self, a, b, c, d):\n        return a\n",
        )
        findings = self._scan()
        self.assertNotIn("REV-002-TOOMANYPARAMS", [f.rule_id for f in findings])

    def test_god_class_rule(self) -> None:
        methods = "\n".join(f"    def m{i}(self):\n        pass\n" for i in range(16))
        self._write("god.py", f"class Big:\n{methods}")
        findings = self._scan()
        god_findings = [f for f in findings if f.rule_id == "REV-003-GODCLASS"]
        self.assertEqual(len(god_findings), 1)
        self.assertEqual(god_findings[0].principle, "SRP")

    def test_deep_nesting_rule(self) -> None:
        self._write(
            "nested.py",
            "def f(x):\n"
            "    if x:\n"
            "        if x:\n"
            "            if x:\n"
            "                if x:\n"
            "                    if x:\n"
            "                        return 1\n",
        )
        findings = self._scan()
        self.assertIn("REV-004-DEEPNESTING", [f.rule_id for f in findings])

    def test_magic_number_rule(self) -> None:
        self._write("magic.py", "def f(x):\n    if x > 8675309:\n        return True\n")
        findings = self._scan()
        self.assertIn("REV-005-MAGICNUMBER", [f.rule_id for f in findings])

    def test_magic_number_rule_allows_common_values(self) -> None:
        self._write("magic_ok.py", "def f(x):\n    if x > 100:\n        return True\n")
        findings = self._scan()
        self.assertNotIn("REV-005-MAGICNUMBER", [f.rule_id for f in findings])

    def test_missing_docstring_rule(self) -> None:
        self._write("nodoc.py", "def public_fn():\n    return 1\n")
        findings = self._scan()
        self.assertIn("REV-006-NODOCSTRING", [f.rule_id for f in findings])

    def test_missing_docstring_ignores_private(self) -> None:
        self._write("private_ok.py", "def _helper():\n    return 1\n")
        findings = self._scan()
        self.assertNotIn("REV-006-NODOCSTRING", [f.rule_id for f in findings])

    def test_missing_docstring_ok_when_present(self) -> None:
        self._write(
            "doc_ok.py", 'def public_fn():\n    """Does a thing."""\n    return 1\n'
        )
        findings = self._scan()
        self.assertNotIn("REV-006-NODOCSTRING", [f.rule_id for f in findings])

    def test_mutable_default_arg_rule(self) -> None:
        self._write(
            "mutdef.py", "def f(items=[]):\n    items.append(1)\n    return items\n"
        )
        findings = self._scan()
        self.assertIn("REV-007-MUTABLEDEFAULT", [f.rule_id for f in findings])

    def test_mutable_default_arg_ok_with_none(self) -> None:
        self._write(
            "mutdef_ok.py",
            "def f(items=None):\n    items = items or []\n    return items\n",
        )
        findings = self._scan()
        self.assertNotIn("REV-007-MUTABLEDEFAULT", [f.rule_id for f in findings])

    def test_type_check_chain_rule(self) -> None:
        self._write(
            "chain.py",
            "def f(shape):\n"
            "    if isinstance(shape, Circle):\n"
            "        return 1\n"
            "    elif isinstance(shape, Square):\n"
            "        return 2\n"
            "    elif isinstance(shape, Triangle):\n"
            "        return 3\n",
        )
        findings = self._scan()
        chain_findings = [f for f in findings if f.rule_id == "REV-008-TYPECHECKCHAIN"]
        self.assertGreaterEqual(len(chain_findings), 1)
        self.assertEqual(chain_findings[0].principle, "OCP")

    def test_type_check_chain_ok_when_short(self) -> None:
        self._write(
            "chain_ok.py",
            "def f(shape):\n"
            "    if isinstance(shape, Circle):\n"
            "        return 1\n"
            "    elif isinstance(shape, Square):\n"
            "        return 2\n",
        )
        findings = self._scan()
        self.assertNotIn("REV-008-TYPECHECKCHAIN", [f.rule_id for f in findings])

    def test_fat_interface_rule(self) -> None:
        methods = "\n".join(
            f"    @abstractmethod\n    def m{i}(self):\n        ...\n" for i in range(8)
        )
        self._write("fat.py", f"class Iface(ABC):\n{methods}")
        findings = self._scan()
        fat_findings = [f for f in findings if f.rule_id == "REV-009-FATINTERFACE"]
        self.assertEqual(len(fat_findings), 1)
        self.assertEqual(fat_findings[0].principle, "ISP")

    def test_concrete_dependency_rule(self) -> None:
        self._write(
            "dip.py",
            "class Widget:\n"
            "    def __init__(self):\n"
            "        self.db = DatabaseService()\n",
        )
        findings = self._scan()
        dip_findings = [f for f in findings if f.rule_id == "REV-010-CONCRETEDEP"]
        self.assertEqual(len(dip_findings), 1)
        self.assertEqual(dip_findings[0].principle, "DIP")

    def test_concrete_dependency_ok_when_injected(self) -> None:
        self._write(
            "dip_ok.py",
            "class Widget:\n"
            "    def __init__(self, db_service):\n"
            "        self.db = db_service\n",
        )
        findings = self._scan()
        self.assertNotIn("REV-010-CONCRETEDEP", [f.rule_id for f in findings])

    def test_rule_disabled_via_policy(self) -> None:
        self._write("nodoc2.py", "def public_fn():\n    return 1\n")
        findings = self._scan(rules={"REV-006-NODOCSTRING": False})
        self.assertEqual(findings, [])

    def test_syntax_error_file_skipped_gracefully(self) -> None:
        self._write("broken.py", "def f(:\n    pass\n")
        findings = self._scan()
        self.assertEqual(findings, [])

    def test_non_python_file_ignored(self) -> None:
        self._write("notes.txt", "def f(a, b, c, d, e, f, g):\n    pass\n")
        findings = self._scan()
        self.assertEqual(findings, [])

    # ─── SOLID Scorer ────────────────────────────────────────────────────────

    def test_solid_scorer_penalizes_relevant_principle(self) -> None:
        finding = ReviewFinding(
            id="1",
            rule_id="REV-003-GODCLASS",
            category="Design",
            title="God Class",
            description="d",
            severity=Severity.MEDIUM,
            confidence="MEDIUM",
            principle="SRP",
            file_path="a.py",
            line_number=1,
            recommendation="r",
            fingerprint="f",
        )
        scores = SolidScorer.score([finding])
        self.assertLess(scores["SRP"], 100.0)  # type: ignore[arg-type]
        self.assertEqual(scores["OCP"], 100.0)

    def test_solid_scorer_lsp_always_none(self) -> None:
        scores = SolidScorer.score([])
        self.assertIsNone(scores["L"])
        self.assertEqual(scores["SRP"], 100.0)

    def test_solid_scorer_score_floors_at_zero(self) -> None:
        findings = [
            ReviewFinding(
                id=str(i),
                rule_id="REV-003-GODCLASS",
                category="Design",
                title="God Class",
                description="d",
                severity=Severity.CRITICAL,
                confidence="MEDIUM",
                principle="SRP",
                file_path="a.py",
                line_number=1,
                recommendation="r",
                fingerprint=str(i),
            )
            for i in range(10)
        ]
        scores = SolidScorer.score(findings)
        self.assertEqual(scores["SRP"], 0.0)

    # ─── Report Generator ────────────────────────────────────────────────────

    def test_report_generator_passed_status_when_no_findings(self) -> None:
        report = ReviewReportGenerator.generate_report(
            "proj", [], llm_review_enabled=False
        )
        self.assertEqual(report.status, "PASSED")
        self.assertEqual(report.quality_score, 100.0)
        self.assertIn("No code quality issues", report.summary)

    def test_report_generator_failed_status_on_heavy_findings(self) -> None:
        findings = [
            ReviewFinding(
                id=str(i),
                rule_id="REV-007-MUTABLEDEFAULT",
                category="Correctness",
                title="Mutable Default Argument",
                description="d",
                severity=Severity.HIGH,
                confidence="HIGH",
                principle=None,
                file_path="a.py",
                line_number=i,
                recommendation="r",
                fingerprint=str(i),
            )
            for i in range(5)
        ]
        report = ReviewReportGenerator.generate_report(
            "proj", findings, llm_review_enabled=False
        )
        self.assertEqual(report.status, "FAILED")
        self.assertLess(report.quality_score, 70.0)

    def test_report_generator_includes_llm_notes_when_enabled(self) -> None:
        finding = ReviewFinding(
            id="1",
            rule_id="REV-001-LONGFUNC",
            category="Complexity",
            title="Function Too Long",
            description="d",
            severity=Severity.MEDIUM,
            confidence="HIGH",
            principle=None,
            file_path="a.py",
            line_number=1,
            recommendation="r",
            fingerprint="f",
        )
        report = ReviewReportGenerator.generate_report(
            "proj", [finding], llm_review_enabled=True, model_router=self.mock_router
        )
        self.assertIn("AI Review Notes", report.summary)

    def test_report_generator_handles_llm_failure_gracefully(self) -> None:
        finding = ReviewFinding(
            id="1",
            rule_id="REV-001-LONGFUNC",
            category="Complexity",
            title="Function Too Long",
            description="d",
            severity=Severity.MEDIUM,
            confidence="HIGH",
            principle=None,
            file_path="a.py",
            line_number=1,
            recommendation="r",
            fingerprint="f",
        )
        failing_router = MagicMock(spec=ModelRouterService)
        failing_router.generate.side_effect = RuntimeError("model unavailable")
        report = ReviewReportGenerator.generate_report(
            "proj", [finding], llm_review_enabled=True, model_router=failing_router
        )
        self.assertNotIn("AI Review Notes", report.summary)

    # ─── Validator ───────────────────────────────────────────────────────────

    def test_validator_rejects_missing_plan(self) -> None:
        validator = ReviewerValidator()
        _, spec, report = self._make_mock_artifacts()
        with self.assertRaises(ReviewerValidationError):
            validator.validate(None, spec, report, self.workspace_path)  # type: ignore[arg-type]

    def test_validator_rejects_missing_workspace(self) -> None:
        validator = ReviewerValidator()
        plan, spec, report = self._make_mock_artifacts()
        with self.assertRaises(ReviewerValidationError):
            validator.validate(plan, spec, report, "/path/does/not/exist")

    def test_validator_accepts_valid_inputs(self) -> None:
        validator = ReviewerValidator()
        plan, spec, report = self._make_mock_artifacts()
        validator.validate(plan, spec, report, self.workspace_path)  # should not raise

    # ─── Writer ──────────────────────────────────────────────────────────────

    def test_writer_writes_all_deliverables(self) -> None:
        writer = ReviewerWorkspaceWriter(self.event_bus_mock)
        report = ReviewReport(
            project_id="proj",
            findings=[],
            quality_score=100.0,
            solid_scores={
                "SRP": 100.0,
                "OCP": 100.0,
                "L": None,
                "ISP": 100.0,
                "DIP": 100.0,
            },
            status="PASSED",
            summary="# Report",
            recommendations=[],
        )
        manifest = ReviewManifest(
            files_scanned=["a.py"],
            scan_duration_ms=5,
            rules_run=["REV-001-LONGFUNC"],
            ignored_files=[],
            tool_version="1.0.0",
            timestamp=0.0,
        )
        writer.write_reports(self.workspace_path, report, manifest)

        self.assertTrue((Path(self.workspace_path) / "review_report.json").exists())
        self.assertTrue((Path(self.workspace_path) / "review_summary.md").exists())
        self.assertTrue((Path(self.workspace_path) / "review_manifest.json").exists())

    def test_writer_raises_on_missing_workspace(self) -> None:
        writer = ReviewerWorkspaceWriter(self.event_bus_mock)
        report = ReviewReport(
            project_id="proj",
            findings=[],
            quality_score=100.0,
            solid_scores={},
            status="PASSED",
            summary="",
            recommendations=[],
        )
        manifest = ReviewManifest([], 0, [], [], "1.0.0", 0.0)
        from forge_plugins.reviewer.exceptions import ReviewerWriteError

        with self.assertRaises(ReviewerWriteError):
            writer.write_reports("/path/does/not/exist", report, manifest)

    # ─── Service Integration (End-to-End) ───────────────────────────────────

    def test_review_project_end_to_end_passes(self) -> None:
        self._write(
            "clean.py",
            'def add(a, b):\n    """Adds two numbers."""\n    return a + b\n',
        )
        plan, spec, report = self._make_mock_artifacts()

        result = self.reviewer_service.review_project(plan, spec, report, None, None)

        self.assertIsInstance(result, ReviewReport)
        self.assertEqual(result.status, "PASSED")
        self.assertTrue((Path(self.workspace_path) / "review_report.json").exists())

    def test_review_project_raises_on_invalid_plan(self) -> None:
        _, spec, report = self._make_mock_artifacts()
        with self.assertRaises(ReviewerValidationError):
            self.reviewer_service.review_project(None, spec, report, None, None)  # type: ignore[arg-type]

    def test_review_project_blocks_release_when_gate_enabled(self) -> None:
        self.full_config.reviewer["block_release"] = True
        self.full_config.reviewer["min_quality_score"] = 99.0
        self._write("mutdef.py", "def f(items=[]):\n    return items\n")
        plan, spec, report = self._make_mock_artifacts()

        with self.assertRaises(ReviewerError):
            self.reviewer_service.review_project(plan, spec, report, None, None)

    def test_review_project_does_not_block_by_default(self) -> None:
        self._write("mutdef.py", "def f(items=[]):\n    return items\n")
        plan, spec, report = self._make_mock_artifacts()

        result = self.reviewer_service.review_project(plan, spec, report, None, None)
        self.assertIsInstance(result, ReviewReport)

    # ─── Plugin Registration ─────────────────────────────────────────────────

    def test_plugin_registers_service(self) -> None:
        plugin = ReviewerPlugin()
        registry = ServiceRegistry()
        registry.register(ModelRouterService, self.mock_router)  # type: ignore[type-abstract]
        registry.register(ConfigurationService, self.mock_config)  # type: ignore[type-abstract]
        registry.register(EventBusService, self.event_bus_mock)  # type: ignore[type-abstract]
        registry.register(MemoryService, self.memory)  # type: ignore[type-abstract]

        plugin.initialize(registry)

        self.assertEqual(plugin.name, "reviewer")
        self.assertIn("solid_scoring", plugin.capabilities)
        plugin.shutdown()

    # ─── Model Serialization ─────────────────────────────────────────────────

    def test_review_finding_round_trip(self) -> None:
        finding = ReviewFinding(
            id="1",
            rule_id="REV-001-LONGFUNC",
            category="Complexity",
            title="t",
            description="d",
            severity=Severity.LOW,
            confidence="HIGH",
            principle=None,
            file_path="a.py",
            line_number=1,
            recommendation="r",
            fingerprint="f",
        )
        restored = ReviewFinding.from_dict(finding.to_dict())
        self.assertEqual(restored, finding)

    def test_review_report_round_trip(self) -> None:
        report = ReviewReport(
            project_id="proj",
            findings=[],
            quality_score=88.5,
            solid_scores={"SRP": 90.0, "L": None},
            status="PASSED",
            summary="s",
            recommendations=["r1"],
        )
        restored = ReviewReport.from_dict(report.to_dict())
        self.assertEqual(restored.quality_score, report.quality_score)
        self.assertIsNone(restored.solid_scores["L"])

    def test_review_manifest_round_trip(self) -> None:
        manifest = ReviewManifest(
            files_scanned=["a.py"],
            scan_duration_ms=10,
            rules_run=["REV-001-LONGFUNC"],
            ignored_files=[],
            tool_version="1.0.0",
            timestamp=123.0,
        )
        restored = ReviewManifest.from_dict(manifest.to_dict())
        self.assertEqual(restored, manifest)


if __name__ == "__main__":
    unittest.main()
