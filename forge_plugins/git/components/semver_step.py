"""
SemverStep — analyses the commit log since the last tag and recommends a version bump.
"""

import logging
import re

from forge_plugins.planner.service import parse_json_response

from ..utils.git_pipeline import GitContext, GitPipelineStep
from ..models import SemverBump

logger = logging.getLogger("ForgeAI.Plugins.Git.Components")

_BUMP_PRIORITIES = {"MAJOR": 3, "MINOR": 2, "PATCH": 1}


def _parse_next_version(current: str, bump_type: str) -> str:
    """
    Computes the next semantic version string.

    Args:
        current (str): Current version string, e.g. '1.2.3' or 'v1.2.3'.
        bump_type (str): One of 'MAJOR', 'MINOR', or 'PATCH'.

    Returns:
        str: Next version string without 'v' prefix.
    """
    cleaned = current.lstrip("v")
    parts = cleaned.split(".")
    if len(parts) != 3:
        parts = ["0", "0", "0"]

    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        major, minor, patch = 0, 0, 0

    if bump_type == "MAJOR":
        return f"{major + 1}.0.0"
    elif bump_type == "MINOR":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"


def _classify_bump_deterministic(commit_log: str) -> str:
    """
    Classifies the bump type from commit messages using conventional commit prefixes.
    Returns 'PATCH' when no strong signals are found.

    Args:
        commit_log (str): Raw one-line commit log from git.

    Returns:
        str: 'MAJOR', 'MINOR', or 'PATCH'.
    """
    log_lower = commit_log.lower()

    if "breaking change" in log_lower or "!:" in log_lower:
        return "MAJOR"
    if re.search(r"\b(feat|feature|add|new)\b", log_lower):
        return "MINOR"
    return "PATCH"


class SemverStep(GitPipelineStep):
    """
    Reads the git commit log since the last tag and recommends a semantic version bump.
    Uses LLM by default; falls back to rule-based classification on LLM failure.
    """

    @property
    def name(self) -> str:
        return "Semver Step"

    def run(self, context: GitContext) -> None:
        """
        Retrieves the commit log, sends it to the LLM, parses the recommended bump,
        and stores the resulting SemverBump in the context.

        Args:
            context (GitContext): The shared pipeline context.
        """
        current_tag = context.git_ops.describe()
        commit_log = context.git_ops.log(
            since_tag=current_tag if current_tag != "0.0.0" else None
        )

        context.logger.info(
            f"Analysing {len(commit_log.splitlines())} commits for semver bump. Current tag: {current_tag}"
        )

        bump_type = self._classify_bump(context, commit_log)
        rationale = (
            f"Determined '{bump_type}' bump from commit history since {current_tag}."
        )
        recommended = _parse_next_version(current_tag, bump_type)

        context.semver = SemverBump(
            current=current_tag,
            recommended=recommended,
            bump_type=bump_type,
            rationale=rationale,
        )
        context.logger.info(
            f"Semver recommendation: {current_tag} → {recommended} ({bump_type})"
        )

    def _classify_bump(self, context: GitContext, commit_log: str) -> str:
        """
        Attempts LLM-based bump classification, with deterministic fallback.

        Args:
            context (GitContext): The shared pipeline context.
            commit_log (str): One-line git commit log.

        Returns:
            str: 'MAJOR', 'MINOR', or 'PATCH'.
        """
        prompt_path = __file__.replace(
            "components/semver_step.py", "prompts/semver.txt"
        ).replace("components\\semver_step.py", "prompts\\semver.txt")

        from pathlib import Path

        prompt_file = Path(prompt_path)
        if not prompt_file.exists():
            # Inline fallback prompt if file missing
            prompt_template = (
                "Analyse the following git commit log and respond with a JSON object containing:\n"
                "- bump_type: one of 'MAJOR', 'MINOR', 'PATCH'\n"
                "- rationale: one-sentence explanation\n\n"
                "Commit log:\n{commit_log}\n\n"
                "Respond with valid JSON only. No markdown, no extra text."
            )
        else:
            prompt_template = prompt_file.read_text(encoding="utf-8")

        prompt = prompt_template.format(
            commit_log=commit_log or "(no commits since last tag)"
        )

        try:
            response = context.model_router.generate(prompt, response_format="json")
            data = parse_json_response(response.text)
            bump_type = str(data.get("bump_type", "PATCH")).upper()
            if bump_type not in _BUMP_PRIORITIES:
                bump_type = "PATCH"
            return bump_type
        except Exception as exc:
            context.logger.warning(
                f"LLM semver classification failed, using rule-based fallback: {exc}"
            )
            return _classify_bump_deterministic(commit_log)
