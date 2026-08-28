"""
Data models representing workflows, workflow execution stages, states, and types.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Type


class WorkflowState(Enum):
    """Represents the lifecycle states of a workflow or workflow stage."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class WorkflowType(Enum):
    """Defines the default engineering workflow pipelines supported by ForgeAI."""

    FULL_ENGINEERING = "FULL_ENGINEERING"
    DOCUMENTATION_ONLY = "DOCUMENTATION_ONLY"
    TEST_ONLY = "TEST_ONLY"
    BUILD_ONLY = "BUILD_ONLY"
    DELIVERY_ONLY = "DELIVERY_ONLY"
    CUSTOM = "CUSTOM"


@dataclass
class WorkflowStage:
    """
    Represents a single step/stage within a workflow execution pipeline.
    """

    name: str
    service_interface: Type[Any]
    method_name: str
    retry_count: int = 2
    retry_delay: float = 2.0
    timeout: float = 180.0
    optional: bool = False
    critical: bool = True
    status: WorkflowState = WorkflowState.PENDING
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts the stage to a dictionary representation."""
        return {
            "name": self.name,
            "service_interface": self.service_interface.__name__,
            "method_name": self.method_name,
            "retry_count": self.retry_count,
            "retry_delay": self.retry_delay,
            "timeout": self.timeout,
            "optional": self.optional,
            "critical": self.critical,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], service_interface: Type[Any]
    ) -> "WorkflowStage":
        """
        Constructs a stage from its dictionary representation.
        """
        return cls(
            name=data["name"],
            service_interface=service_interface,
            method_name=data["method_name"],
            retry_count=data.get("retry_count", 2),
            retry_delay=data.get("retry_delay", 2.0),
            timeout=data.get("timeout", 180.0),
            optional=data.get("optional", False),
            critical=data.get("critical", True),
            status=WorkflowState(data.get("status", "PENDING")),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
        )


@dataclass
class Workflow:
    """
    Represents an orchestrated sequence of engineering pipeline stages.
    """

    id: str
    name: str
    type: WorkflowType
    state: WorkflowState
    stages: List[WorkflowStage]
    current_stage_index: int = 0
    context: Dict[str, Any] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the workflow representation to a dictionary for persistence."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "state": self.state.value,
            "stages": [stage.to_dict() for stage in self.stages],
            "current_stage_index": self.current_stage_index,
            "context": self._serialize_context(),
            "errors": self.errors,
            "progress": self.progress,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def _serialize_context(self) -> Dict[str, Any]:
        """Filters out non-JSON serializable details from the context."""
        import unittest.mock

        serialized: Dict[str, Any] = {}
        for k, v in self.context.items():
            if isinstance(v, unittest.mock.Mock):
                serialized[k] = {"__mock__": True}
            elif hasattr(v, "to_dict") and callable(getattr(v, "to_dict")):
                serialized[k] = v.to_dict()
            elif isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                serialized[k] = v
        return serialized

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], interface_map: Dict[str, Type[Any]]
    ) -> "Workflow":
        """
        Constructs a workflow from its dictionary representation.
        """
        stages = []
        for stage_data in data["stages"]:
            iface_name = stage_data["service_interface"]
            iface = interface_map.get(iface_name)
            if not iface:
                raise ValueError(f"Unknown service interface type: {iface_name}")
            stages.append(WorkflowStage.from_dict(stage_data, iface))

        return cls(
            id=data["id"],
            name=data["name"],
            type=WorkflowType(data["type"]),
            state=WorkflowState(data["state"]),
            stages=stages,
            current_stage_index=data.get("current_stage_index", 0),
            context=data.get("context", {}),
            errors=data.get("errors", {}),
            progress=data.get("progress", 0.0),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )
