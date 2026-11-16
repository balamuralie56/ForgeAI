"""
Immutable data models for the ForgeAI History Engine.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, FrozenSet, List

# Workflow-context keys that hold a plugin's structured report. Each run keeps
# its own copy of these so a later run no longer overwrites an earlier one.
REPORT_KINDS: FrozenSet[str] = frozenset(
    {
        "project_plan",
        "architecture_specification",
        "implementation_report",
        "test_report",
        "documentation_report",
        "security_report",
        "review_report",
        "git_report",
    }
)


@dataclass(frozen=True)
class RunSummary:
    """
    Lightweight description of one workflow run, suitable for list views.

    Attributes:
        workflow_id (str): Unique workflow identifier.
        name (str): Display name of the run.
        goal (str): The natural-language goal the run was started with.
        workflow_type (str): The WorkflowType value (e.g. "BUILD_ONLY").
        state (str): The latest WorkflowState value.
        progress (float): Completion percentage, 0.0 - 100.0.
        model (str): The LLM model that was configured when the run was recorded.
        created_at (float): Unix timestamp of workflow creation.
        updated_at (float): Unix timestamp of the latest recorded snapshot.
    """

    workflow_id: str
    name: str
    goal: str
    workflow_type: str
    state: str
    progress: float
    model: str
    created_at: float
    updated_at: float

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the summary to a plain dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class RunDetail:
    """
    Full description of one workflow run, excluding the (potentially large)
    artifact bodies, which are fetched individually.

    Attributes:
        summary (RunSummary): The run's summary fields.
        stages (List[Dict[str, Any]]): Per-stage status records.
        errors (Dict[str, str]): Stage name to error message.
        artifact_kinds (List[str]): The report kinds stored for this run.
    """

    summary: RunSummary
    stages: List[Dict[str, Any]] = field(default_factory=list)
    errors: Dict[str, str] = field(default_factory=dict)
    artifact_kinds: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the detail to a plain dictionary."""
        return {
            **self.summary.to_dict(),
            "stages": self.stages,
            "errors": self.errors,
            "artifact_kinds": self.artifact_kinds,
        }


@dataclass(frozen=True)
class StorageUsage:
    """
    Storage consumed by the history database.

    Attributes:
        database_bytes (int): On-disk size of the history database file.
        run_count (int): Number of recorded runs.
        artifact_bytes_by_run (Dict[str, int]): Workflow ID to the total size
            in bytes of that run's stored reports.
    """

    database_bytes: int
    run_count: int
    artifact_bytes_by_run: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the usage report to a plain dictionary."""
        return asdict(self)
