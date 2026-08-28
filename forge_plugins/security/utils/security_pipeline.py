"""
Security execution pipeline running scanners concurrently via the Task Engine.
"""

import time
import logging
import asyncio
from typing import Dict, List, Any
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_core.task_engine.service import TaskEngineService
from forge_core.task_engine.models import Task
from forge_core.task_engine.dag import TaskDAG
from forge_plugins.security.models import SecurityFinding

from forge_plugins.security.components.ignore_engine import SecurityIgnoreEngine
from forge_plugins.security.components.secret_scanner import SecretScanner
from forge_plugins.security.components.vulnerability_scanner import (
    DependencyVulnerabilityScanner,
)
from forge_plugins.security.components.static_analyzer import StaticAnalyzer
from forge_plugins.security.components.license_checker import LicenseChecker

logger = logging.getLogger("ForgeAI.Plugins.Security.Pipeline")


class SecurityContext:
    """
    State container passed between scanning pipeline tasks.
    """

    def __init__(self, workspace: str, rule_policy: Dict[str, bool]) -> None:
        self.workspace = workspace
        self.rule_policy = rule_policy
        self.ignore_engine = SecurityIgnoreEngine(workspace)

        self.secret_scanner = SecretScanner(workspace)
        self.vuln_scanner = DependencyVulnerabilityScanner(workspace)
        self.static_analyzer = StaticAnalyzer(workspace, self.ignore_engine)
        self.license_checker = LicenseChecker(workspace)

        # Output states
        self.findings: List[SecurityFinding] = []
        self.files_scanned: List[str] = []
        self.ignored_files: List[str] = []
        self.scan_duration_ms: int = 0


class SecurityPipeline:
    """
    DAG-based pipeline execution manager using the Task Engine.
    """

    def __init__(
        self, task_engine: TaskEngineService, event_bus: EventBusService
    ) -> None:
        self.task_engine = task_engine
        self.event_bus = event_bus

    def execute(self, context: SecurityContext) -> None:
        """
        Submits and executes scanning tasks concurrently via the Task Engine.
        """
        start_time = time.perf_counter()

        # Publish started event
        self.event_bus.publish(
            Event(
                event_type="security.scan.started",
                data={"workspace": context.workspace},
            )
        )

        # Build list of non-ignored files to scan and track ignored files
        workspace_path = context.ignore_engine.workspace
        file_paths: List[str] = []
        try:
            for item in workspace_path.rglob("*"):
                if item.is_file():
                    rel_path = str(item.relative_to(workspace_path))
                    file_paths.append(rel_path)
        except Exception:
            pass

        context.files_scanned = context.ignore_engine.filter_paths(file_paths)
        context.ignored_files = [
            p for p in file_paths if p not in context.files_scanned
        ]

        # Define 4 concurrent tasks
        def run_secret_scan() -> List[Dict[str, Any]]:
            self.event_bus.publish(
                Event(
                    event_type="security.rule.started",
                    data={"scanner": "secret_scanner"},
                )
            )
            res: List[SecurityFinding] = []
            for path in context.files_scanned:
                findings = context.secret_scanner.scan_file(path)
                for f in findings:
                    self.event_bus.publish(
                        Event(event_type="security.finding.detected", data=f.to_dict())
                    )
                res.extend(findings)
            self.event_bus.publish(
                Event(
                    event_type="security.rule.completed",
                    data={"scanner": "secret_scanner"},
                )
            )
            return [f.to_dict() for f in res]

        def run_dependency_scan() -> List[Dict[str, Any]]:
            self.event_bus.publish(
                Event(
                    event_type="security.rule.started",
                    data={"scanner": "dependency_scanner"},
                )
            )
            res = context.vuln_scanner.scan_manifests()
            for f in res:
                self.event_bus.publish(
                    Event(event_type="security.finding.detected", data=f.to_dict())
                )
            self.event_bus.publish(
                Event(
                    event_type="security.rule.completed",
                    data={"scanner": "dependency_scanner"},
                )
            )
            return [f.to_dict() for f in res]

        def run_ast_scan() -> List[Dict[str, Any]]:
            self.event_bus.publish(
                Event(
                    event_type="security.rule.started", data={"scanner": "ast_analyzer"}
                )
            )
            res = context.static_analyzer.scan_files(context.rule_policy)
            for f in res:
                self.event_bus.publish(
                    Event(event_type="security.finding.detected", data=f.to_dict())
                )
            self.event_bus.publish(
                Event(
                    event_type="security.rule.completed",
                    data={"scanner": "ast_analyzer"},
                )
            )
            return [f.to_dict() for f in res]

        def run_license_scan() -> List[Dict[str, Any]]:
            self.event_bus.publish(
                Event(
                    event_type="security.rule.started",
                    data={"scanner": "license_checker"},
                )
            )
            res = context.license_checker.check_licenses()
            for f in res:
                self.event_bus.publish(
                    Event(event_type="security.finding.detected", data=f.to_dict())
                )
            self.event_bus.publish(
                Event(
                    event_type="security.rule.completed",
                    data={"scanner": "license_checker"},
                )
            )
            return [f.to_dict() for f in res]

        task_secrets = Task(
            task_id="sec_secrets",
            name="Secrets Scanning",
            execution_callable=run_secret_scan,
        )
        task_deps = Task(
            task_id="sec_deps",
            name="Dependency Scanning",
            execution_callable=run_dependency_scan,
        )
        task_ast = Task(
            task_id="sec_ast",
            name="Static Analysis (AST)",
            execution_callable=run_ast_scan,
        )
        task_license = Task(
            task_id="sec_license",
            name="License Check",
            execution_callable=run_license_scan,
        )

        dag = TaskDAG([task_secrets, task_deps, task_ast, task_license])
        run_id = self.task_engine.submit_dag(dag)

        # Run the DAG using asyncio within synchronous context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # If running in another async flow, wait for completion using thread/future mapping
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    lambda: asyncio.run(self.task_engine.execute_dag(run_id))
                )
                results = future.result()
        else:
            results = loop.run_until_complete(self.task_engine.execute_dag(run_id))

        # Merge findings
        for task_id, res in results.items():
            if isinstance(res, list):
                for item in res:
                    if isinstance(item, dict):
                        context.findings.append(SecurityFinding.from_dict(item))

        context.scan_duration_ms = int((time.perf_counter() - start_time) * 1000)
