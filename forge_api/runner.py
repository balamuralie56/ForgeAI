"""
Runs a workflow on a background thread so the API can return immediately and
the frontend can poll/stream its progress instead of blocking on the request.
"""

import logging
import threading
from typing import Optional

from forge_core.workflow.models import Workflow
from forge_core.workflow.service import WorkflowService

logger = logging.getLogger("ForgeAI.API.Runner")

_run_lock = threading.Lock()
_active_workflow_id: Optional[str] = None


class WorkflowAlreadyRunningError(Exception):
    """Raised when a second workflow run is requested while one is already in flight."""


def is_running() -> bool:
    """Returns whether a workflow is currently executing on the background thread."""
    return _active_workflow_id is not None


def start_workflow(workflow_service: WorkflowService, workflow: Workflow) -> None:
    """
    Starts running the given workflow on a background thread.

    Raises:
        WorkflowAlreadyRunningError: If another workflow is already running - this
            is a local single-user tool and the Kernel's shared state (config,
            memory connections) isn't designed for concurrent workflow runs.
    """
    global _active_workflow_id

    with _run_lock:
        if _active_workflow_id is not None:
            raise WorkflowAlreadyRunningError(
                f"Workflow '{_active_workflow_id}' is already running. Wait for it to finish."
            )
        _active_workflow_id = workflow.id

    def _run() -> None:
        global _active_workflow_id
        try:
            workflow_service.run_workflow(workflow)
        except Exception as e:
            logger.error(f"Workflow {workflow.id} failed: {e}", exc_info=True)
        finally:
            with _run_lock:
                _active_workflow_id = None

    thread = threading.Thread(
        target=_run, name=f"forge-workflow-{workflow.id[:8]}", daemon=True
    )
    thread.start()
    logger.info(f"Started workflow {workflow.id} on background thread {thread.name}.")
