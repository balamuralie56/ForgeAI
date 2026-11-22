"""
Startup recovery for workflow runs interrupted by a server stop.

Workflows only ever execute inside the API process (see runner.py), so when the
API starts nothing can be running yet. Any run still recorded as PENDING,
RUNNING or WAITING was cut off by the previous process exiting; left alone it
would show as "running" forever and could never be deleted from the UI.
"""

import logging
from typing import List

from forge_core.history.service import HistoryService
from forge_core.workflow.exceptions import WorkflowStateError
from forge_core.workflow.models import WorkflowState
from forge_core.workflow.service import WorkflowService

logger = logging.getLogger("ForgeAI.API.Recovery")

_ACTIVE_STATES = {
    WorkflowState.PENDING.value,
    WorkflowState.RUNNING.value,
    WorkflowState.WAITING.value,
}
_PAGE_SIZE = 200
INTERRUPTED_MESSAGE = (
    "Interrupted: the ForgeAI server stopped before this run finished."
)


def cancel_interrupted_runs(
    history: HistoryService, workflows: WorkflowService
) -> List[str]:
    """
    Marks every run left in an active state as CANCELLED, along with any stage
    that was mid-flight, and records why. Must only be called before any
    workflow starts in this process.

    Args:
        history (HistoryService): Source of recorded runs.
        workflows (WorkflowService): Used to load and cancel each workflow, which
            persists the change to both project memory and history.

    Returns:
        List[str]: IDs of the runs that were cancelled.
    """
    stale: List[str] = []
    offset = 0
    while True:
        page = history.list_runs(limit=_PAGE_SIZE, offset=offset)
        stale.extend(r.workflow_id for r in page if r.state in _ACTIVE_STATES)
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    cancelled: List[str] = []
    for workflow_id in stale:
        workflow = workflows.load_workflow(workflow_id)
        if workflow is None:
            logger.warning(
                f"Run '{workflow_id}' is recorded as active but has no saved workflow "
                "state to recover; leaving it unchanged."
            )
            continue

        for stage in workflow.stages:
            if stage.status in (WorkflowState.RUNNING, WorkflowState.WAITING):
                stage.status = WorkflowState.CANCELLED
                stage.error = INTERRUPTED_MESSAGE
        workflow.errors["interrupted"] = INTERRUPTED_MESSAGE

        try:
            workflows.cancel_workflow(workflow)
        except WorkflowStateError as e:
            logger.error(f"Could not cancel interrupted run '{workflow_id}': {e}")
            continue
        cancelled.append(workflow_id)
        logger.warning(f"Marked interrupted run '{workflow_id}' as CANCELLED.")

    return cancelled
