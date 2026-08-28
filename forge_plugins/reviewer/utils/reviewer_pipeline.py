"""
Review execution pipeline running the static analyzer across the workspace.
"""

import time
import logging
from typing import Dict, List
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_plugins.reviewer.models import ReviewFinding

from forge_plugins.security.components.ignore_engine import SecurityIgnoreEngine
from forge_plugins.reviewer.components.static_analyzer import ReviewStaticAnalyzer

logger = logging.getLogger("ForgeAI.Plugins.Reviewer.Pipeline")


class ReviewerContext:
    """State container passed through the review pipeline."""

    def __init__(self, workspace: str, rule_policy: Dict[str, bool]) -> None:
        self.workspace = workspace
        self.rule_policy = rule_policy
        self.ignore_engine = SecurityIgnoreEngine(workspace)
        self.static_analyzer = ReviewStaticAnalyzer(workspace, self.ignore_engine)

        self.findings: List[ReviewFinding] = []
        self.files_scanned: List[str] = []
        self.ignored_files: List[str] = []
        self.scan_duration_ms: int = 0


class ReviewerPipeline:
    """Runs the review scan and records file/timing manifest data."""

    def __init__(self, event_bus: EventBusService) -> None:
        self.event_bus = event_bus

    def execute(self, context: ReviewerContext) -> None:
        """Executes the static review scan synchronously."""
        start_time = time.perf_counter()

        self.event_bus.publish(
            Event(
                event_type="reviewer.scan.started",
                data={"workspace": context.workspace},
            )
        )

        workspace_path = context.ignore_engine.workspace
        file_paths: List[str] = []
        try:
            for item in workspace_path.rglob("*"):
                if item.is_file():
                    file_paths.append(str(item.relative_to(workspace_path)))
        except Exception:
            pass

        context.files_scanned = context.ignore_engine.filter_paths(file_paths)
        context.ignored_files = [
            p for p in file_paths if p not in context.files_scanned
        ]

        findings = context.static_analyzer.scan_files(context.rule_policy)
        for f in findings:
            self.event_bus.publish(
                Event(event_type="reviewer.finding.detected", data=f.to_dict())
            )
        context.findings = findings

        context.scan_duration_ms = int((time.perf_counter() - start_time) * 1000)

        self.event_bus.publish(
            Event(
                event_type="reviewer.scan.completed",
                data={"workspace": context.workspace, "findings": len(findings)},
            )
        )
