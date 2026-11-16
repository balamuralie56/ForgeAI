"""
FastAPI application exposing ForgeAI's Kernel and Workflow Orchestrator to the
web frontend over REST + a WebSocket event stream.

Run with: uvicorn forge_api.main:app --reload --port 8420
"""

import asyncio
import logging
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from forge_core.configuration.service import ConfigurationService
from forge_core.event_bus.service import EventBusService
from forge_core.history.exceptions import HistoryError
from forge_core.history.models import REPORT_KINDS
from forge_core.history.service import HistoryService
from forge_core.memory.service import MemoryService
from forge_core.workflow.service import WorkflowService
from forge_core.workflow.models import WorkflowType
from forge_core.version import __version__

from . import bootstrap, runner
from .ws_manager import EventBroadcaster
from .schemas import (
    CreateWorkflowRequest,
    CreateWorkflowResponse,
    WorkflowStatusResponse,
    StageStatus,
    FileListResponse,
    FileEntry,
    FileContentResponse,
    ReportResponse,
    DiagnosticsResponse,
    RunSummaryModel,
    RunListResponse,
    RunDetailResponse,
    RunArtifactResponse,
    DeleteRunResponse,
    StorageResponse,
)

logger = logging.getLogger("ForgeAI.API")

# Every report a plugin persists to project memory, keyed exactly as each
# plugin's service.py calls memory.project.set_metadata(key, ...). Explicit
# allowlist so /api/reports/{key} can't be used to read arbitrary memory keys.
_REPORT_KEYS = REPORT_KINDS

_broadcaster: Optional[EventBroadcaster] = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _broadcaster
    kernel = bootstrap.get_kernel()
    event_bus = kernel.registry.resolve(EventBusService)  # type: ignore[type-abstract]
    _broadcaster = EventBroadcaster(event_bus)
    _broadcaster.start(asyncio.get_event_loop())
    logger.info("ForgeAI API started.")

    yield

    if _broadcaster:
        _broadcaster.stop()
    bootstrap.shutdown_kernel()
    logger.info("ForgeAI API stopped.")


app = FastAPI(title="ForgeAI API", version=__version__, lifespan=lifespan)

# The frontend dev server (Vite) runs on a different origin; this API is
# local-only (bound to localhost), so a permissive local CORS policy is fine.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _workflow_service() -> WorkflowService:
    return bootstrap.get_kernel().registry.resolve(WorkflowService)  # type: ignore[type-abstract]


def _config_service() -> ConfigurationService:
    return bootstrap.get_kernel().registry.resolve(ConfigurationService)  # type: ignore[type-abstract]


def _memory_service() -> MemoryService:
    return bootstrap.get_kernel().registry.resolve(MemoryService)  # type: ignore[type-abstract]


def _history_service() -> HistoryService:
    return bootstrap.get_kernel().registry.resolve(HistoryService)  # type: ignore[type-abstract]


@app.get("/api/diagnostics", response_model=DiagnosticsResponse)
def get_diagnostics() -> DiagnosticsResponse:
    """Returns a system diagnostics snapshot, mirroring `launcher.py --diagnostics`."""
    kernel = bootstrap.get_kernel()

    ollama_status = "Offline"
    try:
        with socket.create_connection(("localhost", 11434), timeout=1.0):
            ollama_status = "Online (Listening on port 11434)"
    except Exception:
        pass

    registered_services = list(kernel.health()["services"].keys())
    enabled_plugins = (
        [p.name for p in kernel.plugin_manager.get_all_plugins()]
        if kernel.plugin_manager
        else []
    )
    default_model = _config_service().get_model_settings().default_model

    return DiagnosticsResponse(
        version=__version__,
        python_version=sys.version.split()[0],
        ollama_status=ollama_status,
        registered_services=registered_services,
        enabled_plugins=enabled_plugins,
        default_model=default_model,
    )


@app.post("/api/workflows", response_model=CreateWorkflowResponse, status_code=201)
def create_workflow(payload: CreateWorkflowRequest) -> CreateWorkflowResponse:
    """Creates and starts a new workflow run in the background."""
    try:
        workflow_type = WorkflowType[payload.workflow_type]
    except KeyError:
        raise HTTPException(
            status_code=400, detail=f"Unknown workflow_type: {payload.workflow_type}"
        )

    service = _workflow_service()
    workflow = service.create_workflow(
        workflow_type=workflow_type,
        name=payload.name or payload.goal[:60],
        goal=payload.goal,
    )

    try:
        runner.start_workflow(service, workflow)
    except runner.WorkflowAlreadyRunningError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return CreateWorkflowResponse(workflow_id=workflow.id, status=workflow.state.value)


@app.get("/api/workflows/{workflow_id}", response_model=WorkflowStatusResponse)
def get_workflow(workflow_id: str) -> WorkflowStatusResponse:
    """Returns the current status/progress of a workflow run."""
    service = _workflow_service()
    workflow = service.load_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    data = workflow.to_dict()
    return WorkflowStatusResponse(
        id=data["id"],
        name=data["name"],
        type=data["type"],
        state=data["state"],
        progress=data["progress"],
        stages=[StageStatus(**s) for s in data["stages"]],
        errors=data["errors"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


@app.get("/api/workflows/{workflow_id}/files", response_model=FileListResponse)
def list_workflow_files(workflow_id: str) -> FileListResponse:
    """Lists files generated in the workflow's workspace directory."""
    service = _workflow_service()
    if not service.load_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found.")

    workspace = Path(_config_service().get_system_settings().workspace_dir)
    if not workspace.exists():
        return FileListResponse(workflow_id=workflow_id, files=[])

    files = [
        FileEntry(
            path=str(p.relative_to(workspace)).replace("\\", "/"),
            size_bytes=p.stat().st_size,
        )
        for p in sorted(workspace.rglob("*"))
        if p.is_file()
    ]
    return FileListResponse(workflow_id=workflow_id, files=files)


@app.get(
    "/api/workflows/{workflow_id}/files/{file_path:path}",
    response_model=FileContentResponse,
)
def get_workflow_file(workflow_id: str, file_path: str) -> FileContentResponse:
    """Returns the content of a single file from the workflow's workspace."""
    service = _workflow_service()
    if not service.load_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found.")

    workspace = Path(_config_service().get_system_settings().workspace_dir).resolve()
    target = (workspace / file_path).resolve()

    # Prevent path traversal outside the workspace directory.
    if workspace not in target.parents and target != workspace:
        raise HTTPException(status_code=400, detail="Invalid file path.")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

    return FileContentResponse(path=file_path, content=content)


@app.get("/api/reports/{report_key}", response_model=ReportResponse)
def get_report(report_key: str) -> ReportResponse:
    """
    Returns a plugin's latest structured report - the project plan, architecture
    spec, test/security/review reports, etc. Each plugin already computes and
    persists this; this just reads it back. Reports aren't namespaced per
    workflow (project memory holds the most recent run's data only), matching
    how every plugin service already persists them.
    """
    if report_key not in _REPORT_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown report: {report_key}")

    data = _memory_service().project.get_metadata(report_key)
    if data is None:
        raise HTTPException(
            status_code=404, detail=f"Report '{report_key}' is not available yet."
        )

    return ReportResponse(report=report_key, data=data)


@app.get("/api/history/runs", response_model=RunListResponse)
def list_runs(
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
) -> RunListResponse:
    """Lists recorded workflow runs, newest first."""
    history = _history_service()
    return RunListResponse(
        runs=[RunSummaryModel(**r.to_dict()) for r in history.list_runs(limit, offset)],
        total=history.count_runs(),
        limit=limit,
        offset=offset,
    )


@app.get("/api/history/runs/{workflow_id}", response_model=RunDetailResponse)
def get_run(workflow_id: str) -> RunDetailResponse:
    """Returns one recorded run's stages, errors and the reports it stored."""
    run = _history_service().get_run(workflow_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return RunDetailResponse(**run.to_dict())


@app.get(
    "/api/history/runs/{workflow_id}/artifacts/{kind}",
    response_model=RunArtifactResponse,
)
def get_run_artifact(workflow_id: str, kind: str) -> RunArtifactResponse:
    """
    Returns one plugin report (plan, architecture, tests, ...) exactly as that
    specific run produced it - unlike /api/reports/{key}, later runs never
    overwrite it.
    """
    if kind not in REPORT_KINDS:
        raise HTTPException(status_code=404, detail=f"Unknown report: {kind}")

    data = _history_service().get_artifact(workflow_id, kind)
    if data is None:
        raise HTTPException(
            status_code=404, detail=f"Report '{kind}' is not stored for this run."
        )
    return RunArtifactResponse(workflow_id=workflow_id, kind=kind, data=data)


@app.delete("/api/history/runs/{workflow_id}", response_model=DeleteRunResponse)
def delete_run(workflow_id: str) -> DeleteRunResponse:
    """
    Deletes a recorded run: its history rows, its stored reports, and its
    workflow state in project memory. Generated files are not touched - all
    runs currently share one workspace directory, so they can't be attributed
    to a single run.
    """
    history = _history_service()
    if runner.active_workflow_id() == workflow_id:
        raise HTTPException(
            status_code=409, detail="Cannot delete a run that is still running."
        )
    if history.get_run(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    try:
        history.delete_run(workflow_id)
    except HistoryError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    _memory_service().project.delete_metadata(f"workflow:{workflow_id}")
    return DeleteRunResponse(workflow_id=workflow_id, deleted=True)


@app.get("/api/history/storage", response_model=StorageResponse)
def get_storage() -> StorageResponse:
    """Reports the storage used by recorded history and the generated workspace."""
    usage = _history_service().storage_usage()
    workspace = Path(_config_service().get_system_settings().workspace_dir)
    workspace_bytes = (
        sum(p.stat().st_size for p in workspace.rglob("*") if p.is_file())
        if workspace.exists()
        else 0
    )
    return StorageResponse(
        history_database_bytes=usage.database_bytes,
        run_count=usage.run_count,
        artifact_bytes_by_run=usage.artifact_bytes_by_run,
        workspace_bytes=workspace_bytes,
    )


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    """Streams every ForgeAI event (workflow, plugin, finding) to the client as JSON."""
    await websocket.accept()
    if _broadcaster is None:
        await websocket.close(code=1011)
        return

    client_id, queue = _broadcaster.register()
    try:
        while True:
            message = await queue.get()
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass
    finally:
        _broadcaster.unregister(client_id)
