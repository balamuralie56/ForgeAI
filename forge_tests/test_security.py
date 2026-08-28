"""
Unit and integration tests for the ForgeAI Security Plugin.
"""

import json
import tempfile
import unittest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

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
from forge_core.task_engine.service import TaskEngineService
from forge_core.task_engine.task_engine import ForgeAITaskEngine
from forge_plugins.git.exceptions import GitValidationError

from forge_plugins.planner.models import ProjectPlan, ProjectGoal
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport, GeneratedFile
from forge_plugins.security.models import (
    SecurityFinding,
    SecurityReport,
    SecurityManifest,
    Severity,
)
from forge_plugins.security.exceptions import (
    SecurityValidationError,
    SecurityAnalysisError,
    SecurityWriteError,
    SecurityError,
)
from forge_plugins.security.service import ForgeAISecurity
from forge_plugins.security.plugin import SecurityPlugin
from forge_plugins.git.validators.git_validator import GitValidator


class TestSecurityPlugin(unittest.TestCase):
    """Test suite covering rule checks, components, pipelines, gates, and E2E runs."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_path = self.temp_dir.name

        # Initialize mock services
        self.mock_router = MagicMock(spec=ModelRouterService)
        mock_response = MagicMock(spec=ModelResponse)
        mock_response.text = "AI Remediation: Rewrite using literal_eval."
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
            security={
                "enabled": True,
                "secret_scan": True,
                "dependency_scan": True,
                "ast_scan": True,
                "license_scan": True,
                "llm_review": True,
                "block_release": True,
                "max_risk_score": 30.0,
                "max_high": 2,
                "max_critical": 0,
                "rules": {
                    "SEC-001-EVAL": True,
                    "SEC-002-EXEC": True,
                    "SEC-003-SHELL": True,
                    "SEC-004-PICKLE": True,
                    "SEC-005-WEAKCRYPTO": True,
                    "SEC-006-HARDCODED": True,
                    "SEC-007-SQL": True,
                    "SEC-008-TEMPFILE": True,
                },
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

        # Set up Task Engine
        self.task_engine = ForgeAITaskEngine(
            self.event_bus_mock, self.memory, concurrency_limit=2
        )
        self.task_engine.initialize()
        self.registry.register(TaskEngineService, self.task_engine)  # type: ignore[type-abstract]

        # Initialize Security Service
        self.security_service = ForgeAISecurity(self.registry)
        self.security_service.initialize()

    def tearDown(self) -> None:
        self.security_service.shutdown()
        self.task_engine.shutdown()
        self.memory.shutdown()
        self.temp_dir.cleanup()

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

    # ─── Scanners Checks ─────────────────────────────────────────────────────

    def test_secret_scanner_detects_keys(self) -> None:
        """Verifies SecretScanner flags PEM headers and AWS key tokens."""
        file_path = Path(self.workspace_path) / "keys.py"
        file_path.write_text(
            "AWS_KEY = 'AKIA1234567890123456'\n"
            "PEM_BLOCK = '-----BEGIN RSA PRIVATE KEY-----\\nMIIEowIBAAKCAQ...'\n",
            encoding="utf-8",
        )

        from forge_plugins.security.components.secret_scanner import SecretScanner

        scanner = SecretScanner(self.workspace_path)
        findings = scanner.scan_file("keys.py")

        self.assertEqual(len(findings), 2)
        finding_rule_ids = [f.rule_id for f in findings]
        self.assertIn("SEC-KEY-AWS", finding_rule_ids)
        self.assertIn("SEC-KEY-PEM", finding_rule_ids)

    def test_dependency_vulnerability_scanner(self) -> None:
        """Verifies vulnerability checker flags old insecure dependencies."""
        req_file = Path(self.workspace_path) / "requirements.txt"
        req_file.write_text(
            "django==3.2.0\n" "pyyaml==5.3.1\n" "requests>=2.20.0\n", encoding="utf-8"
        )

        from forge_plugins.security.components.vulnerability_scanner import (
            DependencyVulnerabilityScanner,
        )

        scanner = DependencyVulnerabilityScanner(self.workspace_path)
        findings = scanner.scan_manifests()

        self.assertGreaterEqual(len(findings), 2)
        finding_rules = [f.rule_id for f in findings]
        self.assertIn("DEP-CVE-2024-27351", finding_rules)
        self.assertIn("DEP-CVE-2020-14343", finding_rules)

    def test_license_checker_flags_copyleft(self) -> None:
        """Verifies LicenseChecker raises warnings on GPL/AGPL libraries."""
        req_file = Path(self.workspace_path) / "requirements.txt"
        req_file.write_text("gpl-package==1.0\nagpl-package>=2.0\n", encoding="utf-8")

        from forge_plugins.security.components.license_checker import LicenseChecker

        checker = LicenseChecker(self.workspace_path)
        findings = checker.check_licenses()

        self.assertEqual(len(findings), 2)
        for f in findings:
            self.assertEqual(f.rule_id, "SEC-LIC-GPL")
            self.assertEqual(f.severity, Severity.MEDIUM)

    # ─── AST Rules Checks ────────────────────────────────────────────────────

    def test_ast_rules_check_all_violations(self) -> None:
        """Verifies AST scanner detects insecure patterns inside python source file."""
        code = (
            "import pickle\n"
            "import hashlib\n"
            "import subprocess\n"
            "import tempfile\n"
            "import os\n"
            "\n"
            "def main():\n"
            "    eval('2 + 2')\n"
            "    exec('x = 1')\n"
            "    subprocess.run('ls', shell=True)\n"
            "    db.execute(f'SELECT * FROM users WHERE id = {1}')\n"
            "    pickle.loads(b'data')\n"
            "    hashlib.md5(b'data')\n"
            "    hashlib.new('sha1', b'data')\n"
            "    secret_token = 'super-secret-key-12345'\n"
            "    tempfile.mktemp()\n"
        )
        file_path = Path(self.workspace_path) / "app.py"
        file_path.write_text(code, encoding="utf-8")

        from forge_plugins.security.components.ignore_engine import SecurityIgnoreEngine
        from forge_plugins.security.components.static_analyzer import StaticAnalyzer

        ignore = SecurityIgnoreEngine(self.workspace_path)
        analyzer = StaticAnalyzer(self.workspace_path, ignore)
        findings = analyzer.scan_files(self.full_config.security["rules"])

        self.assertGreaterEqual(len(findings), 8)
        rules_triggered = {f.rule_id for f in findings}
        self.assertIn("SEC-001-EVAL", rules_triggered)
        self.assertIn("SEC-002-EXEC", rules_triggered)
        self.assertIn("SEC-003-SHELL", rules_triggered)
        self.assertIn("SEC-004-PICKLE", rules_triggered)
        self.assertIn("SEC-005-WEAKCRYPTO", rules_triggered)
        self.assertIn("SEC-006-HARDCODED", rules_triggered)
        self.assertIn("SEC-007-SQL", rules_triggered)
        self.assertIn("SEC-008-TEMPFILE", rules_triggered)

    # ─── Ignore Engine ───────────────────────────────────────────────────────

    def test_ignore_engine_respects_forgeignore(self) -> None:
        """Verifies IgnoreEngine filters out paths defined in .forgeignore."""
        ignore_file = Path(self.workspace_path) / ".forgeignore"
        ignore_file.write_text(
            "ignored_file.py\ntests_temp/\n*.log\n", encoding="utf-8"
        )

        from forge_plugins.security.components.ignore_engine import SecurityIgnoreEngine

        engine = SecurityIgnoreEngine(self.workspace_path)

        self.assertTrue(engine.is_ignored("ignored_file.py"))
        self.assertTrue(engine.is_ignored("tests_temp/app.py"))
        self.assertTrue(engine.is_ignored("nested/folder/ignored_file.py"))
        self.assertTrue(engine.is_ignored("manifest.log"))
        self.assertTrue(engine.is_ignored(".venv/lib/site-packages/app.py"))

        self.assertFalse(engine.is_ignored("src/app.py"))
        self.assertFalse(engine.is_ignored("requirements.txt"))

    # ─── Metric Calculations & Report Exports ────────────────────────────────

    def test_metrics_score_calculations(self) -> None:
        """Verifies score calculation and status flags."""
        from forge_plugins.security.components.report_generator import (
            SecurityReportGenerator,
        )

        f1 = SecurityFinding(
            id="f1",
            rule_id="R1",
            category="C",
            title="T",
            description="D",
            severity=Severity.CRITICAL,
            confidence="HIGH",
            cwe=None,
            owasp=None,
            file_path="app.py",
            line_number=1,
            recommendation="R",
            fingerprint="F1",
        )
        f2 = SecurityFinding(
            id="f2",
            rule_id="R2",
            category="C",
            title="T",
            description="D",
            severity=Severity.MEDIUM,
            confidence="MEDIUM",
            cwe=None,
            owasp=None,
            file_path="app.py",
            line_number=2,
            recommendation="R",
            fingerprint="F2",
        )

        risk, sec = SecurityReportGenerator.calculate_scores([f1, f2])
        self.assertEqual(risk, 28.5)
        self.assertEqual(sec, 71.5)

    def test_writer_exports_sarif_manifest(self) -> None:
        """Verifies report writer successfully writes json, markdown, manifest, and SARIF files."""
        plan, spec, report = self._make_mock_artifacts()
        finding = SecurityFinding(
            id="f1",
            rule_id="SEC-001-EVAL",
            category="Injection",
            title="Eval call",
            description="Unsafe eval",
            severity=Severity.CRITICAL,
            confidence="HIGH",
            cwe="CWE-95",
            owasp="A03",
            file_path="app.py",
            line_number=5,
            recommendation="Fix it",
            fingerprint="fp123",
        )

        from forge_plugins.security.components.report_generator import (
            SecurityReportGenerator,
        )

        final_report = SecurityReportGenerator.generate_report(
            "test_proj", [finding], False
        )

        manifest = SecurityManifest(
            files_scanned=["app.py"],
            scan_duration_ms=15,
            rules_run=["SEC-001-EVAL"],
            ignored_files=[],
            tool_version="1.0.0",
            timestamp=time.time(),
        )

        from forge_plugins.security.writers.security_writer import (
            SecurityWorkspaceWriter,
        )

        writer = SecurityWorkspaceWriter(self.event_bus_mock)
        writer.write_reports(self.workspace_path, final_report, manifest)

        self.assertTrue((Path(self.workspace_path) / "security_report.json").exists())
        self.assertTrue((Path(self.workspace_path) / "security_summary.md").exists())
        self.assertTrue((Path(self.workspace_path) / "security_manifest.json").exists())
        self.assertTrue((Path(self.workspace_path) / "sarif.json").exists())

        sarif_content = json.loads(
            (Path(self.workspace_path) / "sarif.json").read_text(encoding="utf-8")
        )
        self.assertEqual(sarif_content["version"], "2.1.0")
        self.assertEqual(len(sarif_content["runs"][0]["results"]), 1)
        self.assertEqual(
            sarif_content["runs"][0]["results"][0]["ruleId"], "SEC-001-EVAL"
        )

    # ─── Release Gates Validation checks ─────────────────────────────────────

    def test_git_quality_release_gates(self) -> None:
        """Verifies the Git pre-flight validator throws GitValidationError when gates are breached."""
        plan, spec, report = self._make_mock_artifacts()

        finding_crit = SecurityFinding(
            id="f1",
            rule_id="SEC-001-EVAL",
            category="Injection",
            title="Eval",
            description="Unsafe eval",
            severity=Severity.CRITICAL,
            confidence="HIGH",
            cwe=None,
            owasp=None,
            file_path="app.py",
            line_number=5,
            recommendation="Fix it",
            fingerprint="fpcrit",
        )

        sec_report = SecurityReport(
            project_id="test_proj",
            findings=[finding_crit],
            risk_score=25.0,
            security_score=75.0,
            status="FAILED",
            summary="# Blocked",
            recommendations=["Fix eval"],
        )

        validator = GitValidator()
        test_rep = MagicMock()
        doc_rep = MagicMock()

        with self.assertRaises(GitValidationError) as context:
            validator.validate(
                plan,
                spec,
                report,
                test_rep,
                doc_rep,
                self.workspace_path,
                self.full_config,
                security_report=sec_report,
            )
        self.assertIn("Release blocked by Security Gate", str(context.exception))

    def test_git_quality_release_gates_pass(self) -> None:
        """Verifies release validator passes when findings are under limits."""
        plan, spec, report = self._make_mock_artifacts()

        finding_low = SecurityFinding(
            id="f1",
            rule_id="SEC-005-WEAKCRYPTO",
            category="Crypto",
            title="MD5",
            description="Insecure MD5",
            severity=Severity.MEDIUM,
            confidence="HIGH",
            cwe=None,
            owasp=None,
            file_path="app.py",
            line_number=5,
            recommendation="Fix MD5",
            fingerprint="fplow",
        )

        sec_report = SecurityReport(
            project_id="test_proj",
            findings=[finding_low],
            risk_score=5.0,
            security_score=95.0,
            status="PASSED",
            summary="# OK",
            recommendations=[],
        )

        validator = GitValidator()
        test_rep = MagicMock()
        doc_rep = MagicMock()

        validator.validate(
            plan,
            spec,
            report,
            test_rep,
            doc_rep,
            self.workspace_path,
            self.full_config,
            security_report=sec_report,
        )

    # ─── End to End E2E Audit Runs ──────────────────────────────────────────

    def test_audit_project_runs_e2e_successfully(self) -> None:
        """Verifies complete end-to-end security audit execution with score trends and events."""
        plan, spec, report = self._make_mock_artifacts()
        test_rep = MagicMock()
        doc_rep = MagicMock()

        app_file = Path(self.workspace_path) / "app.py"
        app_file.write_text("eval('x')\n", encoding="utf-8")
        req_file = Path(self.workspace_path) / "requirements.txt"
        req_file.write_text("django==3.2.0\n", encoding="utf-8")

        self.full_config.security["block_release"] = False

        sec_report = self.security_service.audit_project(
            plan, spec, report, test_rep, doc_rep
        )

        self.assertIsNotNone(sec_report)
        self.assertGreaterEqual(sec_report.risk_score, 25.0)
        self.assertEqual(sec_report.status, "FAILED")

        saved = self.memory.project.get_metadata(f"security:score:{spec.project_id}")
        self.assertIsNotNone(saved)
        self.assertEqual(saved["score"], sec_report.security_score)

        plugin = SecurityPlugin()
        self.assertEqual(plugin.name, "security")
        self.assertIn("sarif_export", plugin.capabilities)

    # ─── Coverage Booster Edge Cases ──────────────────────────────────────────

    def test_analyzer_factory_edge_cases(self) -> None:
        """Verifies AnalyzerFactory and AST parser exceptions handling."""
        from forge_plugins.security.components.analyzer_factory import (
            AnalyzerFactory,
            PythonAnalyzer,
            GenericAnalyzer,
        )

        factory = AnalyzerFactory(self.workspace_path)
        self.assertIsInstance(factory.get_analyzer("app.py"), PythonAnalyzer)
        self.assertIsInstance(factory.get_analyzer("index.js"), GenericAnalyzer)

        analyzer = PythonAnalyzer(self.workspace_path)
        self.assertEqual(analyzer.analyze_file("nonexistent.py", []), [])

        bad_file = Path(self.workspace_path) / "bad.py"
        bad_file.write_text("def class for : 123", encoding="utf-8")
        self.assertEqual(analyzer.analyze_file("bad.py", []), [])

    def test_security_validator_checks(self) -> None:
        """Verifies validator exceptions when artifacts are none or missing properties."""
        from forge_plugins.security.validators.security_validator import (
            SecurityValidator,
        )

        validator = SecurityValidator()
        with self.assertRaises(SecurityValidationError):
            validator.validate(None, MagicMock(), MagicMock(), self.workspace_path)  # type: ignore[arg-type]
        with self.assertRaises(SecurityValidationError):
            validator.validate(MagicMock(), None, MagicMock(), self.workspace_path)  # type: ignore[arg-type]
        with self.assertRaises(SecurityValidationError):
            validator.validate(MagicMock(), MagicMock(), None, self.workspace_path)  # type: ignore[arg-type]
        with self.assertRaises(SecurityValidationError):
            validator.validate(MagicMock(), MagicMock(), MagicMock(), "")  # type: ignore[arg-type]

    def test_empty_findings_report_calculations(self) -> None:
        """Verifies score calculation and summary reports when no findings exist."""
        from forge_plugins.security.components.report_generator import (
            SecurityReportGenerator,
        )

        report = SecurityReportGenerator.generate_report("test_proj", [], False)
        self.assertEqual(report.risk_score, 0.0)
        self.assertEqual(report.security_score, 100.0)
        self.assertIn("No immediate security recommendations.", report.summary)
        self.assertIn(
            "No security violations or vulnerabilities detected.", report.summary
        )

    def test_vulnerability_scanner_missing_files(self) -> None:
        """Verifies Vulnerability Scanner doesn't crash if requirements.txt is missing or invalid."""
        from forge_plugins.security.components.vulnerability_scanner import (
            DependencyVulnerabilityScanner,
        )

        scanner = DependencyVulnerabilityScanner("/nonexistent/workspace")
        self.assertEqual(scanner.scan_manifests(), [])

        # Test bad formats, comments, empty lines
        bad_req = Path(self.workspace_path) / "requirements.txt"
        bad_req.write_text(
            "\n"
            "# This is a comment\n"
            "invalid_package_format_without_version\n"
            "django==3.2.0\n",
            encoding="utf-8",
        )
        scanner_workspace = DependencyVulnerabilityScanner(self.workspace_path)
        findings = scanner_workspace.scan_manifests()
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "DEP-CVE-2024-27351")

        # Test read Exception
        with patch.object(Path, "read_text", side_effect=IOError("Read failure")):
            self.assertEqual(scanner_workspace.scan_manifests(), [])

    def test_vulnerability_scanner_is_vulnerable_helpers(self) -> None:
        """Verifies semver vulnerable calculations including operators and parse errors."""
        from forge_plugins.security.components.vulnerability_scanner import (
            DependencyVulnerabilityScanner,
        )

        scanner = DependencyVulnerabilityScanner(self.workspace_path)

        self.assertTrue(scanner._is_vulnerable("1.2.0", "<", "2.0.0"))
        self.assertTrue(scanner._is_vulnerable("2.0.0", "<=", "2.0.0"))
        self.assertTrue(scanner._is_vulnerable("1.5.0", "==", "1.5.0"))
        self.assertFalse(scanner._is_vulnerable("abc", "==", "1.2.0"))
        # Trigger exception
        self.assertFalse(scanner._is_vulnerable(None, "<", "1.0.0"))  # type: ignore[arg-type]

    def test_license_checker_missing_files(self) -> None:
        """Verifies License Checker doesn't crash on invalid/missing manifest files."""
        from forge_plugins.security.components.license_checker import LicenseChecker

        checker = LicenseChecker("/nonexistent/workspace")
        self.assertEqual(checker.check_licenses(), [])

    def test_service_configuration_resolution_failure(self) -> None:
        """Asserts that audit_project raises SecurityError when workspace configuration cannot be resolved."""
        plan, spec, report = self._make_mock_artifacts()
        self.mock_config.get_system_settings.side_effect = Exception("Config error")

        with self.assertRaises(SecurityError):
            self.security_service.audit_project(
                plan, spec, report, MagicMock(), MagicMock()
            )

    def test_service_validation_failed_logs(self) -> None:
        """Asserts that validator failures publish events and raise error."""
        plan, spec, report = self._make_mock_artifacts()
        self.mock_config.get_system_settings.return_value = self.sys_settings

        with patch.object(
            self.security_service.validator,
            "validate",
            side_effect=SecurityValidationError("Val Error"),
        ):
            with self.assertRaises(SecurityValidationError):
                self.security_service.audit_project(
                    plan, spec, report, MagicMock(), MagicMock()
                )
            publish_calls = self.event_bus_mock.publish.call_args_list
            self.assertGreaterEqual(len(publish_calls), 1)
            event_arg = publish_calls[-1][0][0]
            self.assertEqual(event_arg.event_type, "security.failed")
            self.assertEqual(event_arg.data["error"], "Val Error")

    def test_service_pipeline_execution_failure(self) -> None:
        """Asserts that audit_project raises SecurityAnalysisError when scanner pipeline encounters a crash."""
        plan, spec, report = self._make_mock_artifacts()

        with patch.object(
            self.security_service.pipeline,
            "execute",
            side_effect=Exception("Scan Crash"),
        ):
            with self.assertRaises(SecurityAnalysisError):
                self.security_service.audit_project(
                    plan, spec, report, MagicMock(), MagicMock()
                )
            publish_calls = self.event_bus_mock.publish.call_args_list
            self.assertGreaterEqual(len(publish_calls), 1)
            event_arg = publish_calls[-1][0][0]
            self.assertEqual(event_arg.event_type, "security.failed")
            self.assertEqual(event_arg.data["error"], "Scan Crash")

    def test_trend_historydelta_calculations(self) -> None:
        """Verifies score trend tracker processes previous history values."""
        plan, spec, report = self._make_mock_artifacts()
        test_rep = MagicMock()
        doc_rep = MagicMock()

        self.full_config.security["block_release"] = False
        self.memory.project.set_metadata("security:score:test_proj", {"score": 90.0})

        sec_report = self.security_service.audit_project(
            plan, spec, report, test_rep, doc_rep
        )
        self.assertIn("Security score changed by", sec_report.summary)

    def test_trend_history_database_crashes(self) -> None:
        """Ensures that score delta calculations do not crash the service if memory engine throws exception."""
        plan, spec, report = self._make_mock_artifacts()
        test_rep = MagicMock()
        doc_rep = MagicMock()

        self.full_config.security["block_release"] = False

        with patch.object(
            self.memory.project, "get_metadata", side_effect=Exception("DB Failure")
        ):
            sec_report = self.security_service.audit_project(
                plan, spec, report, test_rep, doc_rep
            )
            self.assertIsNotNone(sec_report)

    def test_llm_explanation_failures_handled(self) -> None:
        """Verifies report generation proceeds even if AI router generate call throws exception."""
        from forge_plugins.security.components.report_generator import (
            SecurityReportGenerator,
        )

        f = SecurityFinding(
            id="f1",
            rule_id="R1",
            category="C",
            title="T",
            description="D",
            severity=Severity.CRITICAL,
            confidence="HIGH",
            cwe=None,
            owasp=None,
            file_path="app.py",
            line_number=1,
            recommendation="R",
            fingerprint="F",
        )

        self.mock_router.generate.side_effect = Exception("LLM connection timeout")

        report = SecurityReportGenerator.generate_report(
            project_id="test_proj",
            findings=[f],
            llm_review_enabled=True,
            model_router=self.mock_router,
        )
        self.assertIsNotNone(report)
        self.assertNotIn("AI Security Remediations", report.summary)

    def test_writer_handling_directory_write_errors(self) -> None:
        """Verifies report writer raises SecurityWriteError on non-writable paths."""
        from forge_plugins.security.writers.security_writer import (
            SecurityWorkspaceWriter,
        )

        writer = SecurityWorkspaceWriter(self.event_bus_mock)
        mock_report = MagicMock()
        mock_manifest = MagicMock()

        with self.assertRaises(SecurityWriteError):
            writer.write_reports(
                "/nonexistent/folder/path/to/security", mock_report, mock_manifest
            )

    def test_plugin_initialize_and_shutdown(self) -> None:
        """Verifies Plugin methods initialize and shutdown register services successfully."""
        plugin = SecurityPlugin()
        mock_registry = MagicMock(spec=ServiceRegistry)

        plugin.initialize(mock_registry)
        mock_registry.register.assert_called_once()
        plugin.shutdown()

    def test_service_quality_gates_failure(self) -> None:
        """Asserts that audit_project raises SecurityError when quality gates are breached on service layer."""
        plan, spec, report = self._make_mock_artifacts()
        test_rep = MagicMock()
        doc_rep = MagicMock()

        app_file = Path(self.workspace_path) / "app.py"
        app_file.write_text("eval('x')\n", encoding="utf-8")

        self.full_config.security["block_release"] = True
        self.full_config.security["max_critical"] = 0

        with self.assertRaises(SecurityError) as ctx:
            self.security_service.audit_project(plan, spec, report, test_rep, doc_rep)
        self.assertIn("Security quality gate failed", str(ctx.exception))

    def test_service_quality_gates_failure_high(self) -> None:
        """Asserts that audit_project raises SecurityError when max_high is breached."""
        plan, spec, report = self._make_mock_artifacts()

        app_file = Path(self.workspace_path) / "app.py"
        app_file.write_text(
            "import subprocess\nsubprocess.run('ls', shell=True)\n", encoding="utf-8"
        )

        self.full_config.security["block_release"] = True
        self.full_config.security["max_critical"] = 10
        self.full_config.security["max_high"] = 0

        with self.assertRaises(SecurityError):
            self.security_service.audit_project(
                plan, spec, report, MagicMock(), MagicMock()
            )

    def test_service_quality_gates_failure_risk(self) -> None:
        """Asserts that audit_project raises SecurityError when max_risk_score is breached."""
        plan, spec, report = self._make_mock_artifacts()

        app_file = Path(self.workspace_path) / "app.py"
        app_file.write_text("eval('x')\n", encoding="utf-8")

        self.full_config.security["block_release"] = True
        self.full_config.security["max_critical"] = 10
        self.full_config.security["max_risk_score"] = 5.0

        with self.assertRaises(SecurityError):
            self.security_service.audit_project(
                plan, spec, report, MagicMock(), MagicMock()
            )

    def test_static_analyzer_no_enabled_rules(self) -> None:
        """Verifies static analyzer return early when no rules are enabled."""
        from forge_plugins.security.components.ignore_engine import SecurityIgnoreEngine
        from forge_plugins.security.components.static_analyzer import StaticAnalyzer

        ignore = SecurityIgnoreEngine(self.workspace_path)
        analyzer = StaticAnalyzer(self.workspace_path, ignore)
        self.assertEqual(analyzer.scan_files({}), [])

    def test_static_analyzer_rglob_failure(self) -> None:
        """Verifies static analyzer handles workspace listing exceptions gracefully."""
        from forge_plugins.security.components.ignore_engine import SecurityIgnoreEngine
        from forge_plugins.security.components.static_analyzer import StaticAnalyzer

        ignore = SecurityIgnoreEngine(self.workspace_path)
        analyzer = StaticAnalyzer(self.workspace_path, ignore)

        with patch.object(Path, "rglob", side_effect=Exception("rglob failure")):
            findings = analyzer.scan_files(self.full_config.security["rules"])
            self.assertEqual(findings, [])

    def test_writer_duplicate_rules_sarif(self) -> None:
        """Verifies SARIF generation processes duplicate rule IDs and optional mappings correctly."""
        from forge_plugins.security.writers.security_writer import (
            SecurityWorkspaceWriter,
        )

        f1 = SecurityFinding(
            id="1",
            rule_id="SEC-001-EVAL",
            category="Injection",
            title="Eval",
            description="Unsafe eval",
            severity=Severity.CRITICAL,
            confidence="HIGH",
            cwe="CWE-95",
            owasp="A03",
            file_path="app.py",
            line_number=5,
            recommendation="Fix",
            fingerprint="fp1",
        )
        f2 = SecurityFinding(
            id="2",
            rule_id="SEC-001-EVAL",
            category="Injection",
            title="Eval",
            description="Another eval",
            severity=Severity.CRITICAL,
            confidence="HIGH",
            cwe=None,
            owasp=None,
            file_path="app.py",
            line_number=10,
            recommendation="Fix",
            fingerprint="fp2",
        )

        writer = SecurityWorkspaceWriter(self.event_bus_mock)
        sarif = writer._generate_sarif([f1, f2])
        self.assertEqual(len(sarif["runs"][0]["results"]), 2)
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["id"], "SEC-001-EVAL")

    def test_ast_rules_extra_violations(self) -> None:
        """Covers all helper branches in rule and scanner checks."""
        code = (
            "import subprocess\n"
            "from os import system\n"
            "import hashlib\n"
            "from hashlib import md5, sha1\n"
            "import pickle\n"
            "\n"
            "def extra(self):\n"
            "    # Multiple targets\n"
            "    x, y = 1, 2\n"
            "    # Assigning to attribute\n"
            "    self.password = 'my-secret'\n"
            "    # Assigning callable\n"
            "    password = get_pass()\n"
            "    # SQL Injection executemany and other formats\n"
            "    db.executemany('SELECT * FROM users WHERE id = %s', [])\n"
            "    executemany('SELECT * FROM users WHERE id = %s', [])\n"
            "    db.execute('SELECT * FROM users WHERE id = ' + str(x))\n"
            "    db.execute('SELECT * FROM users WHERE id = %s' % (y,))\n"
            "    db.execute('SELECT * FROM users WHERE id = {}.format(x)')\n"
            "    # Subprocess popen and other shell methods\n"
            "    subprocess.Popen('ls', shell=True)\n"
            "    subprocess.call('ls', shell=True)\n"
            "    subprocess.run(['ls'], shell=False)\n"
            "    system('ls')\n"
            "    # Hashlib MD5 keyword and empty checks\n"
            "    hashlib.md5(name='test')\n"
            "    hashlib.new('md5', data=b'data')\n"
            "    # Direct md5 and sha1 functions\n"
            "    md5(b'data')\n"
            "    sha1(b'data')\n"
        )
        file_path = Path(self.workspace_path) / "extra.py"
        file_path.write_text(code, encoding="utf-8")

        from forge_plugins.security.components.ignore_engine import SecurityIgnoreEngine
        from forge_plugins.security.components.static_analyzer import StaticAnalyzer

        ignore = SecurityIgnoreEngine(self.workspace_path)
        analyzer = StaticAnalyzer(self.workspace_path, ignore)
        findings = analyzer.scan_files(self.full_config.security["rules"])
        self.assertGreater(len(findings), 0)

    def test_pipeline_running_loop_simulation(self) -> None:
        """Simulates pipeline execution when an event loop is already running."""
        plan, spec, report = self._make_mock_artifacts()
        test_rep = MagicMock()
        doc_rep = MagicMock()

        self.full_config.security["block_release"] = False

        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True

        with patch("asyncio.get_event_loop", return_value=mock_loop):
            with patch.object(self.task_engine, "execute_dag", return_value={}):
                sec_report = self.security_service.audit_project(
                    plan, spec, report, test_rep, doc_rep
                )
                self.assertIsNotNone(sec_report)

    def test_rule_sql_description_property(self) -> None:
        """Verifies sql rule base properties coverage."""
        from forge_plugins.security.rules.sql_injection_rule import SqlInjectionRule

        rule = SqlInjectionRule()
        self.assertIsNotNone(rule.description)

    def test_license_checker_read_error_exception(self) -> None:
        """Verifies License Checker exception handling when read_text raises an error."""
        from forge_plugins.security.components.license_checker import LicenseChecker

        req_file = Path(self.workspace_path) / "requirements.txt"
        req_file.write_text("gpl-package==1.0\n", encoding="utf-8")

        checker = LicenseChecker(self.workspace_path)
        with patch.object(Path, "read_text", side_effect=IOError("Read failure")):
            findings = checker.check_licenses()
            self.assertEqual(findings, [])

    def test_service_write_reports_failure(self) -> None:
        """Verifies audit_project raises SecurityAnalysisError when workspace report writer crashes."""
        plan, spec, report = self._make_mock_artifacts()
        test_rep = MagicMock()
        doc_rep = MagicMock()

        self.full_config.security["block_release"] = False

        with patch.object(
            self.security_service.writer,
            "write_reports",
            side_effect=Exception("Write failed"),
        ):
            with self.assertRaises(SecurityAnalysisError):
                self.security_service.audit_project(
                    plan, spec, report, test_rep, doc_rep
                )

    def test_service_memory_storage_failure(self) -> None:
        """Verifies audit_project proceeds without crashing when memory storage throws an exception."""
        plan, spec, report = self._make_mock_artifacts()
        test_rep = MagicMock()
        doc_rep = MagicMock()

        self.full_config.security["block_release"] = False

        with patch.object(
            self.memory.runtime,
            "set_project_state",
            side_effect=Exception("Memory crash"),
        ):
            sec_report = self.security_service.audit_project(
                plan, spec, report, test_rep, doc_rep
            )
            self.assertIsNotNone(sec_report)

    def test_models_serialization_deserialization(self) -> None:
        """Verifies serialization and deserialization of security report & manifest models."""
        from forge_plugins.security.models import (
            SecurityFinding,
            SecurityReport,
            SecurityManifest,
            Severity,
        )

        finding = SecurityFinding(
            id="f-1",
            rule_id="SEC-001-EVAL",
            category="Injection",
            title="Eval",
            description="Unsafe eval",
            severity=Severity.CRITICAL,
            confidence="HIGH",
            cwe="CWE-95",
            owasp="A03",
            file_path="app.py",
            line_number=5,
            recommendation="Fix it",
            fingerprint="fp123",
        )

        f_dict = finding.to_dict()
        f_deser = SecurityFinding.from_dict(f_dict)
        self.assertEqual(f_deser.id, "f-1")
        self.assertEqual(f_deser.severity, Severity.CRITICAL)

        report = SecurityReport(
            project_id="test_proj",
            findings=[finding],
            risk_score=25.0,
            security_score=75.0,
            status="FAILED",
            summary="Failed audit",
            recommendations=["Fix it"],
        )

        r_dict = report.to_dict()
        r_deser = SecurityReport.from_dict(r_dict)
        self.assertEqual(r_deser.project_id, "test_proj")
        self.assertEqual(len(r_deser.findings), 1)
        self.assertEqual(r_deser.findings[0].id, "f-1")

        manifest = SecurityManifest(
            files_scanned=["app.py"],
            scan_duration_ms=10,
            rules_run=["SEC-001"],
            ignored_files=[],
            tool_version="1.0",
            timestamp=12345.6,
        )

        m_dict = manifest.to_dict()
        m_deser = SecurityManifest.from_dict(m_dict)
        self.assertEqual(m_deser.tool_version, "1.0")
        self.assertEqual(m_deser.timestamp, 12345.6)

    def test_secret_scanner_edge_cases(self) -> None:
        """Verifies SecretScanner handles nonexistent files, directories, and read errors."""
        from forge_plugins.security.components.secret_scanner import SecretScanner

        scanner = SecretScanner(self.workspace_path)

        # Nonexistent file
        self.assertEqual(scanner.scan_file("missing_file.py"), [])

        # Directory check
        sub_dir = Path(self.workspace_path) / "sub_dir"
        sub_dir.mkdir()
        self.assertEqual(scanner.scan_file("sub_dir"), [])

        # Read error exception handling
        dummy_file = Path(self.workspace_path) / "dummy.py"
        dummy_file.write_text("API_KEY = '123'\n", encoding="utf-8")
        with patch.object(Path, "read_text", side_effect=IOError("Read failure")):
            self.assertEqual(scanner.scan_file("dummy.py"), [])
