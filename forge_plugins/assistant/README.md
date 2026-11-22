# Assistant Plugin

A local coding assistant for existing projects: ask questions about the code, or describe a change. ForgeAI proposes the change as a diff, checks it, applies it when you approve, and can undo it. Everything runs on the local model, and every conversation is stored in `forge_data/databases/forge_assistant.db`.

Full design, safety model and API: [forge_docs/modules/assistant.md](../../forge_docs/modules/assistant.md).

## Directory structure
```text
assistant/
├── plugin.py              # Registers AssistantService in the ServiceRegistry
├── service.py             # AssistantService interface, ForgeAIAssistant, TurnHandle (worker-thread turns)
├── models.py              # Conversation, Message, ChangeSet, FileChange, CheckResult, settings
├── store.py               # SQLite persistence (schema-versioned)
├── diffing.py             # Unified diffs for change sets
├── exceptions.py
├── prompts/               # ask_system.txt, edit_system.txt
└── components/
    ├── agent.py           # One turn: context -> stream -> edits -> checks -> retry / auto-fix
    ├── workspace.py       # Safe project access (.gitignore, protected folders, atomic writes)
    ├── code_index.py      # BM25 code search, project outline, per-project cache
    ├── context_builder.py # Token-budgeted prompts and history
    ├── edit_blocks.py     # SEARCH/REPLACE parsing, tolerant matching, whole-file fallback
    ├── snippet_edits.py   # Whole-definition fallback (replace a function/class by name)
    ├── change_verifier.py # Static before/after checks; missing self-attribute check
    ├── check_runner.py    # Runs the user's check command (no shell, timeout, tree kill)
    └── change_applier.py  # Apply / undo with conflict detection and rollback
```

## Example usage
```python
from forge_plugins.assistant.models import AssistantMode
from forge_plugins.assistant.service import AssistantService

assistant = registry.resolve(AssistantService)
conversation = assistant.create_conversation(r"B:\Projects\my-app", check_command="python -m pytest -q")

for event in assistant.start_turn(conversation.id, "Add a --verbose flag to @cli.py", AssistantMode.EDIT).events():
    if event["type"] == "token":
        print(event["text"], end="")
    elif event["type"] == "change_set":
        change_id = event["change_set"]["id"]

change_set, check_message = assistant.apply_change_set(change_id)   # writes files, runs the tests
assistant.revert_change_set(change_id)                               # undo
```

## Configuration
See the `assistant` section of `config/defaults.json`. `FORGE_ASSISTANT_MODEL` and `FORGE_ASSISTANT_CONTEXT_TOKENS` override the model and the context window.

## Tests
`forge_tests/test_assistant.py` (components, agent turns with a scripted model, service, store) and `forge_tests/test_assistant_api.py` (endpoints, streaming, guards).
