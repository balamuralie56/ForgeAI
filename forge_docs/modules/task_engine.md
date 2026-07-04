# Task Engine

The Task Engine is the execution core of ForgeAI. It validates and executes Directed Acyclic Graphs (DAGs) of tasks concurrently, managing dependency tracking, timeouts, and fault-tolerance retry policies with exponential backoff.

## Architecture & Logic
1. **Directed Acyclic Graph (DAG):** Verifies that tasks do not form execution loops using Depth First Search (DFS) cycle-detection.
2. **Asynchronous Concurrent Execution:** Schedules task nodes concurrently on an event-driven loop up to the limits of available thread concurrency slots.
3. **Fault-Tolerance Retries:** Automatically re-attempts failed jobs using exponential backoff scaling and randomized delay jitter.
4. **Cascading Failure Skip:** If a task fails permanently, the scheduler propagates states and automatically marks all downstream children dependent on the failed task as `SKIPPED`.

## Task States
- `PENDING`: Task is queued, awaiting dependency completion.
- `READY`: Dependencies are met; task is ready to run.
- `RUNNING`: The task callback is currently executing.
- `RETRYING`: Task execution failed; waiting to retry.
- `COMPLETED`: Execution completed successfully.
- `FAILED`: All retry attempts failed.
- `CANCELLED`: DAG run was cancelled.
- `SKIPPED`: Dependencies failed, skipping execution.

## Example Usage

```python
import asyncio
from forge_core.task_engine import ForgeAITaskEngine, Task, TaskDAG, RetryPolicy

# Setup engines
event_bus = ...
memory = ...
task_engine = ForgeAITaskEngine(event_bus, memory, concurrency_limit=3)

# Define work actions
async def write_code(task: Task) -> str:
    print(f"Executing: {task.name}")
    return "Code content"

async def test_code(task: Task) -> str:
    print("Testing code...")
    return "All tests passed"

# Setup tasks
policy = RetryPolicy(max_retries=2, initial_delay=1.0)
task_1 = Task("write", "Write Code", write_code, retry_policy=policy)
task_2 = Task("test", "Test Code", test_code, dependencies=["write"])

# Submit and Execute DAG
dag = TaskDAG([task_1, task_2])
run_id = task_engine.submit_dag(dag)

# Execute DAG asynchronously
results = asyncio.run(task_engine.execute_dag(run_id))
print(results)  # {"write": "Code content", "test": "All tests passed"}
```
