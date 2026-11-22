"""
REST + streaming endpoints for the ForgeAI Assistant.

These endpoints read the user's project files and run the user's check
command, so they are locked to the local frontend: every request must carry
the `X-ForgeAI-Client` header (which a cross-site page cannot send without
passing this API's CORS policy) and address the server by a loopback host
name (which defeats DNS-rebinding attacks).
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from forge_core.kernel.exceptions import ServiceNotFoundError
from forge_plugins.assistant.exceptions import (
    AssistantError,
    AssistantStorageError,
    ChangeConflictError,
    ChangeSetNotFoundError,
    ChangeSetStateError,
    ConversationBusyError,
    ConversationNotFoundError,
)
from forge_plugins.assistant.models import AssistantMode
from forge_plugins.assistant.service import AssistantService

from . import bootstrap

logger = logging.getLogger("ForgeAI.API.Assistant")

CLIENT_HEADER = "x-forgeai-client"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_EVENT_POLL_SECONDS = 0.5


def _host_name(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1 : host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def require_local_client(request: Request) -> None:
    """
    Rejects requests that do not come from the local ForgeAI frontend.

    Raises:
        HTTPException: 403 if the client header is missing or the Host is
            not a loopback name.
    """
    if not request.headers.get(CLIENT_HEADER):
        raise HTTPException(status_code=403, detail="Missing X-ForgeAI-Client header.")
    if _host_name(request.headers.get("host", "")) not in _LOOPBACK_HOSTS:
        raise HTTPException(
            status_code=403, detail="The assistant API only answers on localhost."
        )


router = APIRouter(
    prefix="/api/assistant",
    tags=["assistant"],
    dependencies=[Depends(require_local_client)],
)


class CreateConversationRequest(BaseModel):
    """Body of POST /api/assistant/conversations."""

    project_root: str = Field(..., min_length=1)
    title: str = ""
    check_command: str = ""
    auto_fix: bool = False


class UpdateConversationRequest(BaseModel):
    """Body of PATCH /api/assistant/conversations/{id}; omitted fields are unchanged."""

    title: Optional[str] = None
    project_root: Optional[str] = None
    check_command: Optional[str] = None
    auto_fix: Optional[bool] = None


class SendMessageRequest(BaseModel):
    """Body of POST /api/assistant/conversations/{id}/messages."""

    content: str = Field(..., min_length=1, max_length=20000)
    mode: AssistantMode = AssistantMode.ASK
    attached: List[str] = Field(default_factory=list, max_length=20)


def _service() -> AssistantService:
    try:
        return bootstrap.get_kernel().registry.resolve(AssistantService)  # type: ignore[type-abstract]
    except ServiceNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail="The assistant plugin is not enabled (add 'assistant' to plugins.enabled_plugins).",
        ) from e


def _http_error(error: AssistantError) -> HTTPException:
    if isinstance(error, (ConversationNotFoundError, ChangeSetNotFoundError)):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(
        error, (ConversationBusyError, ChangeSetStateError, ChangeConflictError)
    ):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, AssistantStorageError):
        return HTTPException(status_code=500, detail=str(error))
    return HTTPException(status_code=400, detail=str(error))


@router.get("/status")
def get_status() -> Dict[str, Any]:
    """Returns the model and limits the assistant uses, and its storage."""
    service = _service()
    return {**service.status(), "storage": service.storage()}


@router.get("/conversations")
def list_conversations(
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
) -> Dict[str, Any]:
    """Lists conversations, most recently active first."""
    service = _service()
    return {
        "conversations": [
            c.to_dict() for c in service.list_conversations(limit, offset)
        ],
        "total": service.count_conversations(),
    }


@router.post("/conversations", status_code=201)
def create_conversation(payload: CreateConversationRequest) -> Dict[str, Any]:
    """Starts a conversation about a project folder."""
    try:
        conversation = _service().create_conversation(
            payload.project_root,
            title=payload.title,
            check_command=payload.check_command,
            auto_fix=payload.auto_fix,
        )
    except AssistantError as e:
        raise _http_error(e) from e
    return conversation.to_dict()


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> Dict[str, Any]:
    """Returns a conversation with all its messages and change sets."""
    service = _service()
    try:
        conversation = service.get_conversation(conversation_id)
        messages = service.list_messages(conversation_id)
        change_sets = service.list_change_sets(conversation_id)
    except AssistantError as e:
        raise _http_error(e) from e
    return {
        "conversation": conversation.to_dict(),
        "messages": [m.to_dict() for m in messages],
        "change_sets": [c.to_dict() for c in change_sets],
        "busy": conversation_id in service.status()["active_conversations"],
    }


@router.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: str, payload: UpdateConversationRequest
) -> Dict[str, Any]:
    """Changes a conversation's title, project folder, check command or auto-fix."""
    try:
        conversation = _service().update_conversation(
            conversation_id,
            title=payload.title,
            project_root=payload.project_root,
            check_command=payload.check_command,
            auto_fix=payload.auto_fix,
        )
    except AssistantError as e:
        raise _http_error(e) from e
    return conversation.to_dict()


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> Dict[str, Any]:
    """Deletes a conversation and everything stored with it (not project files)."""
    try:
        deleted = _service().delete_conversation(conversation_id)
    except AssistantError as e:
        raise _http_error(e) from e
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"conversation_id": conversation_id, "deleted": True}


@router.get("/conversations/{conversation_id}/files")
def list_project_files(conversation_id: str) -> Dict[str, Any]:
    """Lists the source files of the conversation's project (for attaching)."""
    try:
        files = _service().list_project_files(conversation_id)
    except AssistantError as e:
        raise _http_error(e) from e
    return {"files": files}


@router.post("/conversations/{conversation_id}/messages")
def send_message(
    conversation_id: str, payload: SendMessageRequest
) -> StreamingResponse:
    """
    Sends a request and streams the reply as newline-delimited JSON events
    (see AssistantAgent.run_turn). Closing the connection stops the reply;
    what was generated so far is kept.
    """
    try:
        handle = _service().start_turn(
            conversation_id, payload.content, payload.mode, payload.attached
        )
    except AssistantError as e:
        raise _http_error(e) from e

    async def stream() -> AsyncIterator[bytes]:
        try:
            while True:
                event = await asyncio.to_thread(handle.next_event, _EVENT_POLL_SECONDS)
                if event is None:
                    continue
                yield (json.dumps(event, default=str) + "\n").encode("utf-8")
                if event.get("type") == "done":
                    return
        finally:
            if not handle.finished:
                logger.info(
                    f"Client left conversation {conversation_id} mid-reply; stopping it."
                )
                handle.cancel()

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/conversations/{conversation_id}/stop")
def stop_reply(conversation_id: str) -> Dict[str, Any]:
    """Stops the conversation's reply in progress, if any."""
    return {"stopped": _service().stop_turn(conversation_id)}


@router.post("/conversations/{conversation_id}/check")
def run_check(conversation_id: str) -> Dict[str, Any]:
    """Runs the conversation's check command now and stores the result."""
    try:
        message = _service().run_check(conversation_id)
    except AssistantError as e:
        raise _http_error(e) from e
    return {"message": message.to_dict()}


@router.post("/changes/{change_set_id}/apply")
def apply_change(change_set_id: str) -> Dict[str, Any]:
    """Writes a proposed change to disk, then runs the check command if set."""
    try:
        change_set, check_message = _service().apply_change_set(change_set_id)
    except AssistantError as e:
        raise _http_error(e) from e
    return {
        "change_set": change_set.to_dict(),
        "check_message": check_message.to_dict() if check_message else None,
    }


@router.post("/changes/{change_set_id}/discard")
def discard_change(change_set_id: str) -> Dict[str, Any]:
    """Discards a proposed change without writing it."""
    try:
        change_set = _service().discard_change_set(change_set_id)
    except AssistantError as e:
        raise _http_error(e) from e
    return {"change_set": change_set.to_dict()}


@router.post("/changes/{change_set_id}/revert")
def revert_change(change_set_id: str) -> Dict[str, Any]:
    """Undoes an applied change, restoring the files it modified."""
    try:
        change_set = _service().revert_change_set(change_set_id)
    except AssistantError as e:
        raise _http_error(e) from e
    return {"change_set": change_set.to_dict()}
