"""
Service definitions and implementation for the ForgeAI Tester Plugin.
"""

import logging
import time
from abc import ABC, abstractmethod

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.model_router.service import ModelRouterService
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_core.memory.service import MemoryService
from forge_core.configuration.service import ConfigurationService

from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport

from .models import TestReport
from .exceptions import (
    TesterError,
    TestValidationError,
    TestingInferenceError,
    TesterWriteError,
)
from .validators.implementation_validator import ImplementationValidator
from .writers.test_workspace_writer import TestWorkspaceWriter
from .utils.test_pipeline import TestContext, TestPipeline
from .runners.pytest_runner import PytestRunner
from .runners.coverage_runner import CoverageRunner
from .components import (
    MockGenerator,
    FixtureGenerator,
    UnitTestGenerator,
    IntegrationTestGenerator,
    SmokeTestGenerator,
    RegressionTestGenerator,
    CoverageReportGenerator,
    TestSummaryGenerator,
)

logger = logging.getLogger("ForgeAI.Plugins.Tester")


class TesterService(ABC):
    """
    Interface for the Tester service.
    """

    @abstractmethod
    def test_project(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        report: ImplementationReport,
    ) -> TestReport:
        """
        Generates and executes tests for the project, verifying requirements and coverage.

        Args:
            plan (ProjectPlan): The project plan.
            spec (ArchitectureSpecification): The software architecture spec.
            report (ImplementationReport): The implementation report containing source files.

        Returns:
            TestReport: The generated test report including execution statistics.
        """
        pass


class ForgeAITester(TesterService):
    """
    Concrete Tester Service implementation.
    Validates, generates, merges, executes tests, asserts coverage limits, and records outputs.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        """
        Initializes the tester service.

        Args:
            registry (ServiceRegistry): System service container.
        """
        self._registry = registry
        self.validator = ImplementationValidator()
        self.writer = TestWorkspaceWriter(self._event_bus)
        self.pytest_runner = PytestRunner()
        self.coverage_runner = CoverageRunner()

        # Assemble the sequential test generator pipeline
        self.steps = [
            MockGenerator(),
            FixtureGenerator(),
            UnitTestGenerator(),
            IntegrationTestGenerator(),
            SmokeTestGenerator(),
            RegressionTestGenerator(),
            CoverageReportGenerator(),
            TestSummaryGenerator(),
        ]
        self.pipeline = TestPipeline(self.steps, self._event_bus)

    @property
    def _model_router(self) -> ModelRouterService:
        return self._registry.resolve(ModelRouterService)  # type: ignore[type-abstract]

    @property
    def _event_bus(self) -> EventBusService:
        return self._registry.resolve(EventBusService)  # type: ignore[type-abstract]

    @property
    def _memory(self) -> MemoryService:
        return self._registry.resolve(MemoryService)  # type: ignore[type-abstract]

    @property
    def _config_service(self) -> ConfigurationService:
        return self._registry.resolve(ConfigurationService)  # type: ignore[type-abstract]

    def test_project(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        report: ImplementationReport,
    ) -> TestReport:
        # 1. Resolve workspace path from config
        try:
            system_settings = self._config_service.get_system_settings()
            workspace_path = system_settings.workspace_dir
        except Exception as e:
            logger.error(f"Failed to resolve workspace settings: {e}")
            raise TesterError(f"Configuration resolution failed: {e}") from e

        # 2. Run early validations
        try:
            self.validator.validate(plan, spec, report, workspace_path)
        except TestValidationError as ve:
            logger.error(f"Validation failed: {ve}")
            self._event_bus.publish(
                Event(
                    event_type="tester.validation_failed",
                    data={"project_id": spec.project_id, "error": str(ve)},
                )
            )
            raise

        logger.info(
            f"Initiating test compilation and verification for Project ID: '{spec.project_id}'"
        )

        # 3. Construct Shared Context
        config = self._config_service.get_full_config()
        context = TestContext(
            project_plan=plan,
            architecture=spec,
            implementation_report=report,
            workspace=workspace_path,
            model_router=self._model_router,
            event_bus=self._event_bus,
            configuration=config,
            memory=self._memory,
            logger=logger,
        )

        # 4. Execute Test Generation Pipeline
        try:
            self.pipeline.execute(context)
        except TestingInferenceError as ie:
            logger.error(f"Test generation failed: {ie}")
            self._event_bus.publish(
                Event(
                    event_type="tester.generation_failed",
                    data={"project_id": spec.project_id, "error": str(ie)},
                )
            )
            raise
        except Exception as e:
            logger.error(f"Unexpected pipeline step execution failure: {e}")
            self._event_bus.publish(
                Event(
                    event_type="tester.generation_failed",
                    data={"project_id": spec.project_id, "error": str(e)},
                )
            )
            raise TesterError(f"Test generation pipeline failed: {e}") from e

        # 5. Atomic Test Workspace Write (with code merging support)
        try:
            self.writer.write_files(
                workspace_path,
                context.generated_test_files,
                spec.project_id,
                model_router=self._model_router,
            )
        except TesterWriteError as we:
            logger.error(f"Failed writing test files: {we}")
            self._event_bus.publish(
                Event(
                    event_type="tester.failed",
                    data={
                        "project_id": spec.project_id,
                        "failed_step": "TestWorkspaceWriter",
                        "error": str(we),
                    },
                )
            )
            raise
        except Exception as e:
            logger.error(f"Workspace writing unexpected error: {e}")
            self._event_bus.publish(
                Event(
                    event_type="tester.failed",
                    data={
                        "project_id": spec.project_id,
                        "failed_step": "TestWorkspaceWriter",
                        "error": str(e),
                    },
                )
            )
            raise TesterError(f"Workspace writing failed: {e}") from e

        # 6. Execute pytest suite
        start_time = time.perf_counter()
        logger.info("Executing generated pytest suite...")
        test_stats = self.pytest_runner.run_tests(workspace_path)
        end_time = time.perf_counter()
        execution_time_ms = int((end_time - start_time) * 1000)

        # Check if tests execution encountered errors/failures
        if (
            not test_stats["success"]
            or test_stats["failed"] > 0
            or test_stats["errors"] > 0
        ):
            logger.error(f"Pytest suite execution encountered failures: {test_stats}")
            self._event_bus.publish(
                Event(
                    event_type="tester.execution_failed",
                    data={"project_id": spec.project_id, "pytest_stats": test_stats},
                )
            )
            # Raise exception to notify caller of execution failures
            raise TesterError(f"Pytest execution failed: {test_stats}")

        # 7. Run code coverage runner
        logger.info("Measuring code coverage stats...")
        cov_percentage = self.coverage_runner.run_coverage(workspace_path)

        # Resolve configurable threshold limit from system settings
        cov_threshold = system_settings.coverage_threshold

        # Check if coverage target met
        if cov_percentage < cov_threshold:
            logger.error(
                f"Statements coverage ({cov_percentage}%) is below the required threshold ({cov_threshold}%)"
            )
            self._event_bus.publish(
                Event(
                    event_type="tester.coverage_failed",
                    data={
                        "project_id": spec.project_id,
                        "coverage": cov_percentage,
                        "threshold": cov_threshold,
                    },
                )
            )
            raise TesterError(
                f"Test coverage target failed: actual={cov_percentage}%, threshold={cov_threshold}%"
            )

        # 8. Compile test_manifest.json contents
        manifest_stats = {
            "project_id": spec.project_id,
            "total_tests": test_stats["total"],
            "passed": test_stats["passed"],
            "failed": test_stats["failed"],
            "errors": test_stats["errors"],
            "coverage_percentage": cov_percentage,
            "coverage_threshold": cov_threshold,
            "status": "PASSED",
            "execution_time_ms": execution_time_ms,
        }

        # Write manifest file to disk
        self.writer.write_manifest(workspace_path, manifest_stats)

        # Retrieve summary report contents
        report_summary = ""
        for tf in context.generated_test_files:
            if tf.test_type == "summary":
                report_summary = tf.content
                break

        # 9. Create final TestReport dataclass
        test_report = TestReport(
            project_id=spec.project_id,
            test_files=context.generated_test_files,
            coverage_summary=f"Coverage of {cov_percentage}% successfully met threshold ({cov_threshold}%).",
            status="SUCCESS",
            summary=report_summary,
        )

        # 10. Record report details into memory service
        try:
            report_dict = test_report.to_dict()
            self._memory.runtime.set_project_state("test_report", report_dict)
            self._memory.project.set_metadata("test_report", report_dict)
        except Exception as e:
            logger.error(f"Failed to record test report in memory registry: {e}")

        # 11. Publish completed event to Bus
        self._event_bus.publish(
            Event(
                event_type="tester.completed",
                data={
                    "project_id": spec.project_id,
                    "stats": manifest_stats,
                },
            )
        )

        logger.info("Test execution and verification completed successfully.")
        return test_report
