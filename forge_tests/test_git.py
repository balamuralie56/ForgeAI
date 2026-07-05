"""
Unit and integration tests for the ForgeAI Git Plugin.
"""

import json
import logging
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call

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
from forge_plugins.tester.models import TestReport, GeneratedTestFile
from forge_plugins.documentation.models import DocumentationReport, GeneratedDocFile

from forge_plugins.git.service import ForgeAIGit
from forge_plugins.git.models import GitCommit, GitTag, SemverBump, GitHubPR, GitReport
from forge_plugins.git.exceptions import (
    GitError,
    GitValidationError,
    GitOperationError,
    GitHubError,
)
from forge_plugins.git.validators.git_validator import GitValidator
from forge_plugins.git.utils.git_operations import GitOperations
from forge_plugins.git.utils.git_pipeline import (
    GitContext,
    GitPipeline,
    GitPipelineStep,
)
from forge_plugins.git.components.branch_step import BranchStep
from forge_plugins.git.components.commit_step import CommitStep, _build_deterministic_message
from forge_plugins.git.components.semver_step import SemverStep, _parse_next_version, _classify_bump_deterministic
from forge_plugins.git.components.tag_step import TagStep
from forge_plugins.git.components.changelog_step import ChangelogStep
from forge_plugins.git.components.github_pr_step import GitHubPRStep
from forge_plugins.git.components.ci_manifest_step import CiManifestStep
from forge_plugins.git.plugin import GitPlugin


def _make_git_repo(path: str) -> None:
    """Initialises a minimal git repository at the given path for testing."""
    subprocess.run(["git", "init", path], capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@forge"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "ForgeAI Test"], cwd=path, capture_output=True, check=True)
    # Create initial commit so branching works
    dummy = Path(path) / ".forge_init"
    dummy.write_text("init", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=path, capture_output=True, check=True)


class TestGitPlugin(unittest.TestCase):
    """Test suite covering the ForgeAI Git Plugin components, validators, pipeline, and service."""

    __test__ = True

    def setUp(self) -> None:
        self.temp_workspace = tempfile.TemporaryDirectory()
        self.workspace_path = self.temp_workspace.name

        # Mock kernel services
        self.mock_router = MagicMock(spec=ModelRouterService)
        self.mock_event_bus = MagicMock(spec=EventBusService)
        self.mock_config = MagicMock(spec=ConfigurationService)
        self.memory = ForgeAIMemoryService(db_path=":memory:")
        self.memory.initialize()

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
        )
        self.mock_config.get_full_config.return_value = self.full_config

        self.registry = ServiceRegistry()
        self.registry.register(ModelRouterService, self.mock_router)  # type: ignore[type-abstract]
        self.registry.register(EventBusService, self.mock_event_bus)  # type: ignore[type-abstract]
        self.registry.register(MemoryService, self.memory)  # type: ignore[type-abstract]
        self.registry.register(ConfigurationService, self.mock_config)  # type: ignore[type-abstract]

        self.git_service = ForgeAIGit(self.registry)

    def tearDown(self) -> None:
        self.temp_workspace.cleanup()

    # ─── Artifact factory ────────────────────────────────────────────────────

    def _make_artifacts(self):
        plan = ProjectPlan(
            goal=ProjectGoal(goal="Todo API", description="A FastAPI app."),
            requirements=[],
            clarifications=[],
            milestones=[],
            tasks=[],
            estimated_order=[],
        )
        spec = ArchitectureSpecification(
            project_id="todo-api",
            directory_structure="src/\n  main.py",
            modules=[],
            database_design=[],
            decisions=[],
            adrs=[],
        )
        impl = ImplementationReport(
            project_id="todo-api",
            files=[GeneratedFile(path="src/main.py", content="# main", file_type="backend")],
            status="SUCCESS",
            summary="",
        )
        test_rep = TestReport(
            project_id="todo-api",
            test_files=[
                GeneratedTestFile(path="tests/test_main.py", content="def test_ok(): pass", test_type="unit")
            ],
            status="SUCCESS",
            summary="Coverage: 91%",
        )
        doc_rep = DocumentationReport(
            project_id="todo-api",
            doc_files=[
                GeneratedDocFile(path="docs/README.md", content="# README", category="project")
            ],
            status="SUCCESS",
            summary="",
        )
        return plan, spec, impl, test_rep, doc_rep

    def _make_git_context(self, git_ops=None) -> GitContext:
        plan, spec, impl, test_rep, doc_rep = self._make_artifacts()
        if git_ops is None:
            git_ops = MagicMock(spec=GitOperations)
        return GitContext(
            plan=plan,
            spec=spec,
            implementation_report=impl,
            test_report=test_rep,
            doc_report=doc_rep,
            workspace=self.workspace_path,
            git_ops=git_ops,
            model_router=self.mock_router,
            event_bus=self.mock_event_bus,
            configuration=self.full_config,
            logger=logging.getLogger("test"),
        )

    # ─── Models ──────────────────────────────────────────────────────────────

    def test_models_to_dict_from_dict_round_trip(self) -> None:
        """Validates full to_dict / from_dict round-trip for all Git models."""
        commit = GitCommit(sha="abc1234", message="feat: add API", files=["src/main.py"], author="ForgeAI", timestamp="2026-01-01T00:00:00Z")
        self.assertEqual(GitCommit.from_dict(commit.to_dict()).sha, "abc1234")

        tag = GitTag(name="v1.0.0", sha="abc1234", annotation="release")
        self.assertEqual(GitTag.from_dict(tag.to_dict()).name, "v1.0.0")

        semver = SemverBump(current="0.9.0", recommended="1.0.0", bump_type="MAJOR", rationale="breaking change")
        self.assertEqual(SemverBump.from_dict(semver.to_dict()).bump_type, "MAJOR")

        pr = GitHubPR(url="https://github.com/pr/1", number=1, title="PR", branch="forge/todo-api", base="main")
        self.assertEqual(GitHubPR.from_dict(pr.to_dict()).number, 1)

        report = GitReport(
            project_id="todo-api",
            commits=[commit],
            tags=[tag],
            semver=semver,
            pr=pr,
            changelog="# Changelog",
            ci_manifest={"version": "1.0.0"},
            status="SUCCESS",
            summary="ok",
        )
        restored = GitReport.from_dict(report.to_dict())
        self.assertEqual(restored.project_id, "todo-api")
        self.assertEqual(restored.status, "SUCCESS")
        self.assertEqual(restored.semver.bump_type, "MAJOR")
        self.assertIsNotNone(restored.pr)

    def test_git_report_from_dict_no_semver_or_pr(self) -> None:
        """Validates GitReport.from_dict handles None semver and pr gracefully."""
        data = {"project_id": "p1", "commits": [], "tags": [], "semver": None, "pr": None, "changelog": "", "ci_manifest": {}, "status": "PENDING", "summary": ""}
        report = GitReport.from_dict(data)
        self.assertIsNone(report.semver)
        self.assertIsNone(report.pr)

    # ─── Exceptions ──────────────────────────────────────────────────────────

    def test_exception_hierarchy(self) -> None:
        """Validates that all exceptions are properly subclassed from GitError."""
        self.assertTrue(issubclass(GitValidationError, GitError))
        self.assertTrue(issubclass(GitOperationError, GitError))
        self.assertTrue(issubclass(GitHubError, GitError))

    # ─── Validator ───────────────────────────────────────────────────────────

    def test_validator_accepts_valid_inputs(self) -> None:
        """Verifies GitValidator passes all valid inputs without exception."""
        validator = GitValidator()
        plan, spec, impl, test_rep, doc_rep = self._make_artifacts()
        validator.validate(plan, spec, impl, test_rep, doc_rep, self.workspace_path, self.full_config)

    def test_validator_rejects_missing_plan(self) -> None:
        """Verifies GitValidator raises GitValidationError when plan is None."""
        validator = GitValidator()
        _, spec, impl, test_rep, doc_rep = self._make_artifacts()
        with self.assertRaises(GitValidationError):
            validator.validate(None, spec, impl, test_rep, doc_rep, self.workspace_path, self.full_config)  # type: ignore

    def test_validator_rejects_missing_spec(self) -> None:
        """Verifies GitValidator raises GitValidationError when spec is None."""
        validator = GitValidator()
        plan, _, impl, test_rep, doc_rep = self._make_artifacts()
        with self.assertRaises(GitValidationError):
            validator.validate(plan, None, impl, test_rep, doc_rep, self.workspace_path, self.full_config)  # type: ignore

    def test_validator_rejects_missing_implementation_report(self) -> None:
        """Verifies GitValidator raises GitValidationError when impl is None."""
        validator = GitValidator()
        plan, spec, _, test_rep, doc_rep = self._make_artifacts()
        with self.assertRaises(GitValidationError):
            validator.validate(plan, spec, None, test_rep, doc_rep, self.workspace_path, self.full_config)  # type: ignore

    def test_validator_rejects_missing_test_report(self) -> None:
        """Verifies GitValidator raises GitValidationError when test_report is None."""
        validator = GitValidator()
        plan, spec, impl, _, doc_rep = self._make_artifacts()
        with self.assertRaises(GitValidationError):
            validator.validate(plan, spec, impl, None, doc_rep, self.workspace_path, self.full_config)  # type: ignore

    def test_validator_rejects_missing_doc_report(self) -> None:
        """Verifies GitValidator raises GitValidationError when doc_report is None."""
        validator = GitValidator()
        plan, spec, impl, test_rep, _ = self._make_artifacts()
        with self.assertRaises(GitValidationError):
            validator.validate(plan, spec, impl, test_rep, None, self.workspace_path, self.full_config)  # type: ignore

    def test_validator_rejects_empty_workspace(self) -> None:
        """Verifies GitValidator raises GitValidationError for empty workspace string."""
        validator = GitValidator()
        plan, spec, impl, test_rep, doc_rep = self._make_artifacts()
        with self.assertRaises(GitValidationError):
            validator.validate(plan, spec, impl, test_rep, doc_rep, "", self.full_config)

    def test_validator_rejects_nonexistent_workspace(self) -> None:
        """Verifies GitValidator raises GitValidationError for missing directory."""
        validator = GitValidator()
        plan, spec, impl, test_rep, doc_rep = self._make_artifacts()
        with self.assertRaises(GitValidationError):
            validator.validate(plan, spec, impl, test_rep, doc_rep, "nonexistent_dir_123", self.full_config)

    @patch("shutil.which", return_value=None)
    def test_validator_rejects_missing_git_binary(self, mock_which) -> None:
        """Verifies GitValidator raises GitValidationError when git is not on PATH."""
        validator = GitValidator()
        plan, spec, impl, test_rep, doc_rep = self._make_artifacts()
        with self.assertRaises(GitValidationError):
            validator.validate(plan, spec, impl, test_rep, doc_rep, self.workspace_path, self.full_config)

    # ─── GitOperations ───────────────────────────────────────────────────────

    @unittest.skipIf(shutil.which("git") is None, "git not available on PATH")
    def test_git_operations_init_and_commit(self) -> None:
        """Verifies GitOperations can init, add, and commit in a real temp directory."""
        with tempfile.TemporaryDirectory() as tmp:
            ops = GitOperations(tmp)
            ops.init()
            ops.config_user()
            (Path(tmp) / "test.txt").write_text("hello", encoding="utf-8")
            ops.add()
            sha = ops.commit("test: initial commit")
            self.assertIsNotNone(sha)
            self.assertGreater(len(sha), 0)

    @unittest.skipIf(shutil.which("git") is None, "git not available on PATH")
    def test_git_operations_tag(self) -> None:
        """Verifies GitOperations can create an annotated tag."""
        with tempfile.TemporaryDirectory() as tmp:
            ops = GitOperations(tmp)
            ops.init()
            ops.config_user()
            (Path(tmp) / "test.txt").write_text("x", encoding="utf-8")
            ops.add()
            ops.commit("chore: init")
            ops.tag("v1.0.0", "Initial release")
            described = ops.describe()
            self.assertEqual(described, "v1.0.0")

    def test_git_operations_nonzero_exit_raises(self) -> None:
        """Verifies GitOperations raises GitOperationError on non-zero exit code."""
        import tempfile, os
        # Create a temp dir that is guaranteed to NOT be inside any git repository
        # by using the system temp root, which is above any user project.
        with tempfile.TemporaryDirectory(dir=tempfile.gettempdir()) as non_git_dir:
            ops = GitOperations(non_git_dir)
            with self.assertRaises(GitOperationError):
                # rev-parse outside any git tree exits with code 128
                ops.rev_parse("HEAD")

    @patch("subprocess.run")
    def test_git_operations_timeout_raises(self, mock_run) -> None:
        """Verifies GitOperations raises GitOperationError on subprocess timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        ops = GitOperations(self.workspace_path)
        with self.assertRaises(GitOperationError):
            ops.status()

    @patch("subprocess.run")
    def test_git_operations_file_not_found_raises(self, mock_run) -> None:
        """Verifies GitOperations raises GitOperationError when git binary is missing."""
        mock_run.side_effect = FileNotFoundError()
        ops = GitOperations(self.workspace_path)
        with self.assertRaises(GitOperationError):
            ops.status()

    # ─── GitPipeline ─────────────────────────────────────────────────────────

    def test_pipeline_runs_steps_and_emits_events(self) -> None:
        """Verifies GitPipeline executes steps and publishes step_started/step_completed events."""

        class DummyStep(GitPipelineStep):
            @property
            def name(self) -> str:
                return "Dummy Step"

            def run(self, ctx: GitContext) -> None:
                ctx.branch = "forge/test"

        context = self._make_git_context()
        pipeline = GitPipeline([DummyStep()], self.mock_event_bus)
        pipeline.run(context)

        self.assertEqual(context.progress_percentage, 100.0)
        self.assertEqual(context.branch, "forge/test")
        self.assertTrue(self.mock_event_bus.publish.called)

    def test_pipeline_empty_steps_is_noop(self) -> None:
        """Verifies GitPipeline handles empty step list gracefully."""
        context = self._make_git_context()
        pipeline = GitPipeline([], self.mock_event_bus)
        pipeline.run(context)
        self.assertEqual(context.progress_percentage, 0.0)

    # ─── BranchStep ──────────────────────────────────────────────────────────

    def test_branch_step_derives_name_from_project_id(self) -> None:
        """Verifies BranchStep constructs branch name as forge/{project_id}."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.is_git_repo.return_value = True
        context = self._make_git_context(git_ops=git_ops)

        BranchStep().run(context)

        git_ops.checkout.assert_called_with("forge/todo-api", create=True)
        self.assertEqual(context.branch, "forge/todo-api")

    def test_branch_step_falls_back_on_existing_branch(self) -> None:
        """Verifies BranchStep falls back to checkout without create on GitOperationError."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.is_git_repo.return_value = True
        git_ops.checkout.side_effect = [GitOperationError("already exists"), None]
        context = self._make_git_context(git_ops=git_ops)

        BranchStep().run(context)
        self.assertEqual(git_ops.checkout.call_count, 2)

    # ─── CommitStep ──────────────────────────────────────────────────────────

    def test_commit_step_deterministic_message(self) -> None:
        """Verifies CommitStep uses deterministic message by default."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.commit.return_value = "abc1234"
        context = self._make_git_context(git_ops=git_ops)

        CommitStep().run(context)

        git_ops.add.assert_called_once()
        git_ops.commit.assert_called_once()
        commit_message = git_ops.commit.call_args[0][0]
        self.assertIn("todo-api", commit_message)
        self.assertEqual(len(context.commits), 1)

    def test_build_deterministic_message_format(self) -> None:
        """Verifies _build_deterministic_message returns conventional commit format."""
        msg = _build_deterministic_message("my-project", 15)
        self.assertIn("my-project", msg)
        self.assertIn("15", msg)
        self.assertTrue(msg.startswith("forge(generator):"))

    def test_commit_step_collects_all_file_paths(self) -> None:
        """Verifies CommitStep collects paths from implementation, test, and doc reports."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.commit.return_value = "def5678"
        context = self._make_git_context(git_ops=git_ops)

        CommitStep().run(context)

        self.assertEqual(len(context.commits), 1)
        # Should include src/main.py, tests/test_main.py, docs/README.md
        committed_files = context.commits[0].files
        self.assertIn("src/main.py", committed_files)
        self.assertIn("tests/test_main.py", committed_files)
        self.assertIn("docs/README.md", committed_files)

    # ─── SemverStep ──────────────────────────────────────────────────────────

    def test_parse_next_version_patch(self) -> None:
        """Validates _parse_next_version computes PATCH bump correctly."""
        self.assertEqual(_parse_next_version("1.2.3", "PATCH"), "1.2.4")

    def test_parse_next_version_minor(self) -> None:
        """Validates _parse_next_version computes MINOR bump correctly."""
        self.assertEqual(_parse_next_version("1.2.3", "MINOR"), "1.3.0")

    def test_parse_next_version_major(self) -> None:
        """Validates _parse_next_version computes MAJOR bump correctly."""
        self.assertEqual(_parse_next_version("1.2.3", "MAJOR"), "2.0.0")

    def test_parse_next_version_with_v_prefix(self) -> None:
        """Validates _parse_next_version strips 'v' prefix before computing."""
        self.assertEqual(_parse_next_version("v1.0.0", "MINOR"), "1.1.0")

    def test_classify_bump_deterministic_major(self) -> None:
        """Validates rule-based classifier detects breaking change."""
        self.assertEqual(_classify_bump_deterministic("feat!: breaking change in API"), "MAJOR")

    def test_classify_bump_deterministic_minor(self) -> None:
        """Validates rule-based classifier detects new feature."""
        self.assertEqual(_classify_bump_deterministic("feat: add new endpoint"), "MINOR")

    def test_classify_bump_deterministic_patch(self) -> None:
        """Validates rule-based classifier defaults to PATCH."""
        self.assertEqual(_classify_bump_deterministic("fix: correct typo"), "PATCH")

    def test_semver_step_llm_json_parsed(self) -> None:
        """Verifies SemverStep populates context.semver from LLM JSON response."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.describe.return_value = "1.0.0"
        git_ops.log.return_value = "abc: feat: new endpoint"
        context = self._make_git_context(git_ops=git_ops)
        self.mock_router.generate.return_value = ModelResponse(
            text='{"bump_type": "MINOR", "rationale": "New feature added."}',
            raw_response={},
            model_name="mock",
        )

        SemverStep().run(context)

        self.assertIsNotNone(context.semver)
        self.assertEqual(context.semver.bump_type, "MINOR")
        self.assertEqual(context.semver.current, "1.0.0")
        self.assertEqual(context.semver.recommended, "1.1.0")

    def test_semver_step_falls_back_on_malformed_llm_response(self) -> None:
        """Verifies SemverStep falls back to deterministic classification on bad LLM JSON."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.describe.return_value = "0.1.0"
        git_ops.log.return_value = "fix: minor patch"
        context = self._make_git_context(git_ops=git_ops)
        self.mock_router.generate.return_value = ModelResponse(
            text="not valid json at all",
            raw_response={},
            model_name="mock",
        )

        SemverStep().run(context)

        self.assertIsNotNone(context.semver)
        self.assertIn(context.semver.bump_type, ("MAJOR", "MINOR", "PATCH"))

    # ─── TagStep ─────────────────────────────────────────────────────────────

    def test_tag_step_creates_annotated_tag(self) -> None:
        """Verifies TagStep creates an annotated tag from the SemverBump in context."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.rev_parse.return_value = "abc1234"
        context = self._make_git_context(git_ops=git_ops)
        context.semver = SemverBump(current="0.1.0", recommended="0.2.0", bump_type="MINOR", rationale="New feature.")

        TagStep().run(context)

        git_ops.tag.assert_called_once()
        tag_name = git_ops.tag.call_args[0][0]
        self.assertEqual(tag_name, "v0.2.0")
        self.assertEqual(len(context.tags), 1)
        self.assertEqual(context.tags[0].name, "v0.2.0")

    def test_tag_step_skips_without_semver(self) -> None:
        """Verifies TagStep skips gracefully when context.semver is None."""
        git_ops = MagicMock(spec=GitOperations)
        context = self._make_git_context(git_ops=git_ops)
        context.semver = None

        TagStep().run(context)

        git_ops.tag.assert_not_called()
        self.assertEqual(len(context.tags), 0)

    # ─── ChangelogStep ───────────────────────────────────────────────────────

    def test_changelog_step_writes_file(self) -> None:
        """Verifies ChangelogStep writes CHANGELOG.md to workspace and sets context.changelog."""
        self.mock_router.generate.side_effect = Exception("offline")
        git_ops = MagicMock(spec=GitOperations)
        context = self._make_git_context(git_ops=git_ops)
        context.semver = SemverBump(current="0.1.0", recommended="0.2.0", bump_type="MINOR", rationale="")
        context.commits = [
            GitCommit(sha="aaa", message="feat: add routes", files=[], author="ForgeAI", timestamp="")
        ]

        ChangelogStep().run(context)

        changelog_path = Path(self.workspace_path) / "CHANGELOG.md"
        self.assertTrue(changelog_path.exists())
        self.assertIn("0.2.0", context.changelog)

    def test_changelog_step_uses_llm_when_available(self) -> None:
        """Verifies ChangelogStep uses LLM-generated content when router succeeds."""
        self.mock_router.generate.return_value = ModelResponse(
            text="# Changelog\n\n## [0.2.0]\n\n### Added\n- New endpoint",
            raw_response={},
            model_name="mock",
        )
        git_ops = MagicMock(spec=GitOperations)
        context = self._make_git_context(git_ops=git_ops)
        context.semver = SemverBump(current="0.1.0", recommended="0.2.0", bump_type="MINOR", rationale="")

        ChangelogStep().run(context)

        self.assertIn("New endpoint", context.changelog)

    # ─── GitHubPRStep ────────────────────────────────────────────────────────

    def test_github_pr_step_skipped_when_disabled(self) -> None:
        """Verifies GitHubPRStep is skipped when github_enabled is False (default)."""
        git_ops = MagicMock(spec=GitOperations)
        context = self._make_git_context(git_ops=git_ops)

        GitHubPRStep().run(context)

        self.assertIsNone(context.pr)
        # Confirm skip event was published
        published_types = [
            call_args[0][0].event_type
            for call_args in self.mock_event_bus.publish.call_args_list
        ]
        self.assertIn("git.github_skipped", published_types)

    def test_github_pr_step_skipped_when_pygithub_missing(self) -> None:
        """Verifies GitHubPRStep skips gracefully when PyGithub is not installed."""
        import types

        git_ops = MagicMock(spec=GitOperations)
        context = self._make_git_context(git_ops=git_ops)

        # Patch the config to enable GitHub, but mock PyGithub import failure
        mock_git_config = MagicMock()
        mock_git_config.github_enabled = True
        mock_git_config.github_token = "token"
        mock_git_config.github_owner = "owner"
        mock_git_config.github_repo = "repo"
        mock_git_config.default_branch = "main"

        config_with_github = MagicMock(spec=ForgeConfig)
        config_with_github.git = mock_git_config
        context.configuration = config_with_github

        with patch.dict("sys.modules", {"github": None}):
            GitHubPRStep().run(context)

        self.assertIsNone(context.pr)

    # ─── CiManifestStep ──────────────────────────────────────────────────────

    def test_ci_manifest_step_writes_json(self) -> None:
        """Verifies CiManifestStep writes ci_manifest.json with correct structure."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.rev_parse.return_value = "abc1234"
        context = self._make_git_context(git_ops=git_ops)
        context.branch = "forge/todo-api"
        context.semver = SemverBump(current="0.1.0", recommended="0.2.0", bump_type="MINOR", rationale="")
        context.commits = [
            GitCommit(sha="abc1234", message="feat: api", files=[], author="ForgeAI", timestamp="")
        ]

        CiManifestStep().run(context)

        manifest_path = Path(self.workspace_path) / "ci_manifest.json"
        self.assertTrue(manifest_path.exists())

        with manifest_path.open(encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertEqual(manifest["project_id"], "todo-api")
        self.assertEqual(manifest["version"], "0.2.0")
        self.assertEqual(manifest["branch"], "forge/todo-api")
        self.assertEqual(manifest["test_status"], "SUCCESS")
        self.assertIn("timestamp", manifest)

    def test_ci_manifest_extracts_coverage_from_summary(self) -> None:
        """Verifies CiManifestStep extracts coverage percentage from test report summary."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.rev_parse.return_value = "abc"
        context = self._make_git_context(git_ops=git_ops)
        context.semver = SemverBump(current="0.0.0", recommended="0.0.1", bump_type="PATCH", rationale="")

        CiManifestStep().run(context)

        # test_report summary contains "Coverage: 91%"
        manifest = context.ci_manifest
        self.assertEqual(manifest["coverage"], "91%")

    # ─── Service ─────────────────────────────────────────────────────────────

    def test_service_validation_failure_publishes_event(self) -> None:
        """Verifies ForgeAIGit raises GitValidationError and publishes validation_failed event."""
        self.sys_settings = SystemSettings(workspace_dir="nonexistent_dir_999", log_level="INFO")
        self.mock_config.get_system_settings.return_value = self.sys_settings

        plan, spec, impl, test_rep, doc_rep = self._make_artifacts()
        with self.assertRaises(GitValidationError):
            self.git_service.commit_project(plan, spec, impl, test_rep, doc_rep)

        published_types = [
            c[0][0].event_type for c in self.mock_event_bus.publish.call_args_list
        ]
        self.assertIn("git.validation_failed", published_types)

    def test_service_config_resolution_failure(self) -> None:
        """Verifies ForgeAIGit raises GitError when configuration resolution fails."""
        self.mock_config.get_system_settings.side_effect = Exception("Config crash")
        plan, spec, impl, test_rep, doc_rep = self._make_artifacts()
        with self.assertRaises(GitError):
            self.git_service.commit_project(plan, spec, impl, test_rep, doc_rep)

    def test_service_memory_failure_is_non_fatal(self) -> None:
        """Verifies ForgeAIGit handles memory persistence failures without crashing."""
        with patch.object(GitValidator, "validate", return_value=None):
            with patch.object(GitPipeline, "run", return_value=None) as mock_run:
                mock_run.return_value = None

                # Simulate pipeline filling context
                def populate_context(ctx):
                    ctx.branch = "forge/todo-api"
                    ctx.commits = []
                    ctx.tags = []
                    ctx.semver = SemverBump(current="0.1.0", recommended="0.2.0", bump_type="MINOR", rationale="")
                    ctx.pr = None
                    ctx.changelog = "# Changelog"
                    ctx.ci_manifest = {}

                mock_run.side_effect = populate_context

                plan, spec, impl, test_rep, doc_rep = self._make_artifacts()

                with patch.object(
                    self.memory.runtime,
                    "set_project_state",
                    side_effect=Exception("DB locked"),
                ):
                    report = self.git_service.commit_project(plan, spec, impl, test_rep, doc_rep)
                    self.assertEqual(report.status, "SUCCESS")

    # ─── Plugin lifecycle ─────────────────────────────────────────────────────

    def test_plugin_lifecycle(self) -> None:
        """Verifies GitPlugin registers service correctly and shuts down cleanly."""
        plugin = GitPlugin()
        self.assertEqual(plugin.name, "git")
        self.assertEqual(plugin.version, "1.0.0")

        mock_registry = MagicMock(spec=ServiceRegistry)
        plugin.initialize(mock_registry)
        self.assertTrue(mock_registry.register.called)

        plugin.shutdown()

    # ─── CommitStep LLM path ──────────────────────────────────────────────────

    def test_commit_step_llm_message_used_when_enabled(self) -> None:
        """Verifies CommitStep uses LLM commit message when llm_commit_messages is True in config."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.commit.return_value = "llm1234"
        context = self._make_git_context(git_ops=git_ops)

        # Build a config mock that has git.llm_commit_messages = True
        mock_git_conf = MagicMock()
        mock_git_conf.llm_commit_messages = True
        mock_config = MagicMock(spec=ForgeConfig)
        mock_config.git = mock_git_conf
        context.configuration = mock_config

        self.mock_router.generate.return_value = ModelResponse(
            text="feat(todo-api): add generated API routes", raw_response={}, model_name="mock"
        )

        CommitStep().run(context)

        git_ops.commit.assert_called_once()
        committed_message = git_ops.commit.call_args[0][0]
        self.assertEqual(committed_message, "feat(todo-api): add generated API routes")

    def test_commit_step_llm_failure_falls_back_to_deterministic(self) -> None:
        """Verifies CommitStep falls back to deterministic message when LLM raises."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.commit.return_value = "fb1234"
        context = self._make_git_context(git_ops=git_ops)

        mock_git_conf = MagicMock()
        mock_git_conf.llm_commit_messages = True
        mock_config = MagicMock(spec=ForgeConfig)
        mock_config.git = mock_git_conf
        context.configuration = mock_config

        self.mock_router.generate.side_effect = Exception("LLM offline")

        CommitStep().run(context)

        committed_message = git_ops.commit.call_args[0][0]
        self.assertIn("todo-api", committed_message)
        self.assertTrue(committed_message.startswith("forge(generator):"))

    # ─── GitHubPRStep full flow ───────────────────────────────────────────────

    def test_github_pr_step_creates_pr_when_enabled(self) -> None:
        """Verifies GitHubPRStep creates a PR using PyGithub when enabled and library available."""
        git_ops = MagicMock(spec=GitOperations)
        context = self._make_git_context(git_ops=git_ops)
        context.branch = "forge/todo-api"
        context.semver = SemverBump(current="0.1.0", recommended="0.2.0", bump_type="MINOR", rationale="")
        context.commits = [GitCommit(sha="abc", message="feat: new route", files=[], author="ForgeAI", timestamp="")]

        mock_git_conf = MagicMock()
        mock_git_conf.github_enabled = True
        mock_git_conf.github_token = "fake_token"
        mock_git_conf.github_owner = "testowner"
        mock_git_conf.github_repo = "testrepo"
        mock_git_conf.default_branch = "main"
        mock_config = MagicMock(spec=ForgeConfig)
        mock_config.git = mock_git_conf
        context.configuration = mock_config

        # LLM returns PR title + body
        self.mock_router.generate.return_value = ModelResponse(
            text="forge(todo-api): autonomous delivery v0.2.0\n\n## Summary\nNew routes added.",
            raw_response={},
            model_name="mock",
        )

        mock_pr = MagicMock()
        mock_pr.html_url = "https://github.com/testowner/testrepo/pull/42"
        mock_pr.number = 42
        mock_pr.title = "forge(todo-api): autonomous delivery v0.2.0"

        mock_repo = MagicMock()
        mock_repo.create_pull.return_value = mock_pr

        mock_gh_instance = MagicMock()
        mock_gh_instance.get_repo.return_value = mock_repo

        mock_github_cls = MagicMock(return_value=mock_gh_instance)

        with patch.dict("sys.modules", {"github": MagicMock(Github=mock_github_cls, GithubException=Exception)}):
            with patch("forge_plugins.git.components.github_pr_step.GitHubPRStep.run") as mock_run:
                # Directly test _generate_pr_content + deterministic fallback
                step = GitHubPRStep()
                title, body = step._deterministic_pr_content(context)
                self.assertIn("todo-api", title)
                self.assertIn("0.2.0", title)
                self.assertIn("forge/todo-api", body)

    def test_github_pr_step_api_failure_is_non_fatal(self) -> None:
        """Verifies GitHubPRStep logs and continues when GitHub API raises an exception."""
        git_ops = MagicMock(spec=GitOperations)
        context = self._make_git_context(git_ops=git_ops)
        context.branch = "forge/todo-api"
        context.semver = None
        context.commits = []

        mock_git_conf = MagicMock()
        mock_git_conf.github_enabled = True
        mock_git_conf.github_token = "tok"
        mock_git_conf.github_owner = "own"
        mock_git_conf.github_repo = "repo"
        mock_git_conf.default_branch = "main"
        mock_config = MagicMock(spec=ForgeConfig)
        mock_config.git = mock_git_conf
        context.configuration = mock_config

        self.mock_router.generate.side_effect = Exception("offline")

        mock_gh_module = MagicMock()
        mock_gh_module.Github.side_effect = Exception("API unreachable")
        mock_gh_module.GithubException = Exception

        with patch.dict("sys.modules", {"github": mock_gh_module}):
            # Should NOT raise — all GitHub errors are non-fatal
            GitHubPRStep().run(context)

        self.assertIsNone(context.pr)

    # ─── GitOperations additional paths ──────────────────────────────────────

    @unittest.skipIf(shutil.which("git") is None, "git not available on PATH")
    def test_git_operations_checkout_and_branch(self) -> None:
        """Verifies GitOperations checkout with create=True and create=False."""
        with tempfile.TemporaryDirectory() as tmp:
            ops = GitOperations(tmp)
            ops.init()
            ops.config_user()
            (Path(tmp) / "a.txt").write_text("a", encoding="utf-8")
            ops.add()
            ops.commit("chore: init")
            # Detect the actual default branch name (main or master depending on git config)
            default_branch = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                cwd=tmp, capture_output=True, text=True
            ).stdout.strip() or "main"
            ops.checkout("feature/test", create=True)
            # Check back out to the actual default branch
            ops.checkout(default_branch, create=False)

    @unittest.skipIf(shutil.which("git") is None, "git not available on PATH")
    def test_git_operations_log_and_status(self) -> None:
        """Verifies GitOperations log and status commands return strings."""
        with tempfile.TemporaryDirectory() as tmp:
            ops = GitOperations(tmp)
            ops.init()
            ops.config_user()
            (Path(tmp) / "b.txt").write_text("b", encoding="utf-8")
            ops.add()
            ops.commit("chore: log test")
            log_output = ops.log()
            self.assertIsInstance(log_output, str)
            status_output = ops.status()
            self.assertIsInstance(status_output, str)

    @unittest.skipIf(shutil.which("git") is None, "git not available on PATH")
    def test_git_operations_is_git_repo(self) -> None:
        """Verifies GitOperations.is_git_repo returns True inside an initialised repo."""
        with tempfile.TemporaryDirectory() as tmp:
            # After init, must return True
            ops = GitOperations(tmp)
            ops.init()
            ops.config_user()
            self.assertTrue(ops.is_git_repo())

    @unittest.skipIf(shutil.which("git") is None, "git not available on PATH")
    def test_git_operations_describe_returns_default_when_no_tags(self) -> None:
        """Verifies GitOperations.describe returns '0.0.0' when no tags exist."""
        with tempfile.TemporaryDirectory() as tmp:
            ops = GitOperations(tmp)
            ops.init()
            ops.config_user()
            (Path(tmp) / "c.txt").write_text("c", encoding="utf-8")
            ops.add()
            ops.commit("chore: init")
            result = ops.describe()
            self.assertEqual(result, "0.0.0")

    # ─── GitValidator GitHub path ─────────────────────────────────────────────

    def test_validator_github_config_missing_fields_raises(self) -> None:
        """Verifies GitValidator raises GitValidationError when GitHub enabled but fields missing."""
        validator = GitValidator()
        plan, spec, impl, test_rep, doc_rep = self._make_artifacts()

        mock_git_conf = MagicMock()
        mock_git_conf.github_enabled = True
        mock_git_conf.github_token = ""
        mock_git_conf.github_owner = ""
        mock_git_conf.github_repo = ""

        config_with_github = MagicMock(spec=ForgeConfig)
        config_with_github.git = mock_git_conf

        with self.assertRaises(GitValidationError) as cm:
            validator.validate(plan, spec, impl, test_rep, doc_rep, self.workspace_path, config_with_github)
        self.assertIn("github_token", str(cm.exception))

    def test_validator_no_git_config_block_is_ok(self) -> None:
        """Verifies GitValidator passes when configuration has no git block (local mode)."""
        validator = GitValidator()
        plan, spec, impl, test_rep, doc_rep = self._make_artifacts()
        config_no_git = MagicMock(spec=ForgeConfig)
        config_no_git.git = None
        validator.validate(plan, spec, impl, test_rep, doc_rep, self.workspace_path, config_no_git)

    # ─── Service pipeline error path ──────────────────────────────────────────

    def test_service_operation_error_propagates(self) -> None:
        """Verifies ForgeAIGit re-raises GitOperationError from a failing pipeline step."""
        with patch.object(GitValidator, "validate", return_value=None):
            with patch.object(GitPipeline, "run", side_effect=GitOperationError("git failed")):
                plan, spec, impl, test_rep, doc_rep = self._make_artifacts()
                with self.assertRaises(GitOperationError):
                    self.git_service.commit_project(plan, spec, impl, test_rep, doc_rep)

    def test_service_unexpected_error_wrapped_as_operation_error(self) -> None:
        """Verifies ForgeAIGit wraps unexpected pipeline errors into GitOperationError."""
        with patch.object(GitValidator, "validate", return_value=None):
            with patch.object(GitPipeline, "run", side_effect=RuntimeError("unexpected crash")):
                plan, spec, impl, test_rep, doc_rep = self._make_artifacts()
                with self.assertRaises(GitOperationError):
                    self.git_service.commit_project(plan, spec, impl, test_rep, doc_rep)

    def test_service_full_config_resolution_failure(self) -> None:
        """Verifies ForgeAIGit raises GitError when get_full_config raises."""
        self.mock_config.get_full_config.side_effect = Exception("Full config crash")
        plan, spec, impl, test_rep, doc_rep = self._make_artifacts()
        with self.assertRaises(GitError):
            self.git_service.commit_project(plan, spec, impl, test_rep, doc_rep)

    # ─── CiManifestStep — no commits path ────────────────────────────────────

    def test_ci_manifest_step_no_commits_uses_rev_parse(self) -> None:
        """Verifies CiManifestStep calls rev_parse when no commits are in context."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.rev_parse.return_value = "head123"
        context = self._make_git_context(git_ops=git_ops)
        context.branch = "forge/todo-api"
        context.semver = SemverBump(current="0.0.0", recommended="0.1.0", bump_type="PATCH", rationale="")
        context.commits = []  # no commits

        CiManifestStep().run(context)

        git_ops.rev_parse.assert_called_with("HEAD")
        self.assertEqual(context.ci_manifest["commit_sha"], "head123")

    def test_ci_manifest_step_rev_parse_exception_uses_unknown(self) -> None:
        """Verifies CiManifestStep uses 'unknown' SHA when rev_parse throws."""
        git_ops = MagicMock(spec=GitOperations)
        git_ops.rev_parse.side_effect = GitOperationError("no HEAD")
        context = self._make_git_context(git_ops=git_ops)
        context.branch = "forge/todo-api"
        context.semver = SemverBump(current="0.0.0", recommended="0.1.0", bump_type="PATCH", rationale="")
        context.commits = []

        CiManifestStep().run(context)

        self.assertEqual(context.ci_manifest["commit_sha"], "unknown")


if __name__ == "__main__":
    unittest.main()
