# History Engine

The History Engine keeps a durable, **per-run** record of every workflow and the reports each one produced, so past runs can be listed, reopened, and deleted.

## Why it exists
Plugins persist their reports to Project Memory under single, fixed keys (`project_plan`, `test_report`, ...). Each new run overwrites the previous one, and Project Memory has no way to list runs. The History Engine fixes both: every run keeps its own copy of its reports, in its own relational tables.

## Core Architecture
1. **Separate database.** History lives in `forge_data/databases/forge_history.db`, not in the Memory Engine's key-value store. Runs own artifacts (`ON DELETE CASCADE`), which the key-value model cannot express.
2. **Interface + DI.** Depend on `HistoryService` (resolved from the `ServiceRegistry`), never on `ForgeAIHistoryService`.
3. **Versioned schema.** The schema version is stored in SQLite's `PRAGMA user_version`. A database written by a newer schema is refused instead of being silently corrupted.
4. **Non-intrusive capture.** `WorkflowOrchestrator` mirrors a workflow snapshot into history every time it persists workflow state. If no `HistoryService` is registered the step is skipped, and a history failure is logged but never fails a workflow. Plugins are untouched.

## Data model
| Table | Purpose |
|---|---|
| `runs` | One row per workflow: name, goal, type, state, progress, model, timestamps, per-stage status, errors |
| `artifacts` | One row per (run, report kind): the plugin report as JSON, with its size |

Report kinds: `project_plan`, `architecture_specification`, `implementation_report`, `test_report`, `documentation_report`, `security_report`, `review_report`, `git_report`.

An artifact whose content has not changed between snapshots is not rewritten. Deleting a run compacts the database (`VACUUM`) so the disk space is actually returned.

## Usage
```python
from forge_core.history.service import HistoryService

history = registry.resolve(HistoryService)
for run in history.list_runs(limit=20):
    print(run.workflow_id, run.state, run.goal)

plan = history.get_artifact(run.workflow_id, "project_plan")
history.delete_run(run.workflow_id)
print(history.storage_usage().database_bytes)
```

## API
| Endpoint | Description |
|---|---|
| `GET /api/history/runs?limit&offset` | Recorded runs, newest first, with a total count |
| `GET /api/history/runs/{id}` | One run's stages, errors, and the report kinds it stored |
| `GET /api/history/runs/{id}/artifacts/{kind}` | A report exactly as that run produced it |
| `DELETE /api/history/runs/{id}` | Deletes the run, its reports, and its workflow state in Project Memory. `409` if it is still running |
| `GET /api/history/storage` | History database size, per-run report sizes, and workspace size |

## Known limits
- Runs recorded before this engine existed are not imported.
- Generated files are **not** deleted with a run: every run currently writes into the one shared `forge_workspace/`, so files cannot be attributed to a single run.
- Only plugin reports and run state are stored. Chat conversations are a planned follow-up.
