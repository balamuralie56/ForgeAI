"""
Pydantic request/response models for the ForgeAI Web API.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CreateWorkflowRequest(BaseModel):
    """Request body to start a new engineering workflow."""

    goal: str = Field(..., min_length=1, description="What you want ForgeAI to build.")
    name: Optional[str] = Field(None, description="Optional display name for the run.")
    workflow_type: str = Field(
        "FULL_ENGINEERING",
        description="One of: FULL_ENGINEERING, DOCUMENTATION_ONLY, TEST_ONLY, BUILD_ONLY, DELIVERY_ONLY.",
    )


class StageStatus(BaseModel):
    """Status of a single pipeline stage."""

    name: str
    status: str
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    optional: bool = False
    critical: bool = True


class WorkflowStatusResponse(BaseModel):
    """Full status snapshot of a workflow run."""

    id: str
    name: str
    type: str
    state: str
    progress: float
    stages: List[StageStatus]
    errors: Dict[str, str] = Field(default_factory=dict)
    created_at: Optional[float] = None
    updated_at: Optional[float] = None


class CreateWorkflowResponse(BaseModel):
    """Returned immediately after starting a workflow; the run itself continues in the background."""

    workflow_id: str
    status: str


class FileEntry(BaseModel):
    """A single file in the generated project workspace."""

    path: str
    size_bytes: int


class FileListResponse(BaseModel):
    """Listing of files generated in a workflow's workspace."""

    workflow_id: str
    files: List[FileEntry]


class FileContentResponse(BaseModel):
    """Content of a single generated file."""

    path: str
    content: str


class DiagnosticsResponse(BaseModel):
    """System diagnostics snapshot, mirroring `launcher.py --diagnostics`."""

    version: str
    python_version: str
    ollama_status: str
    registered_services: List[str]
    enabled_plugins: List[str]
    default_model: str


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    detail: str


class EventMessage(BaseModel):
    """A single event forwarded over the WebSocket stream."""

    event_type: str
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str
