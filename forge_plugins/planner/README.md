# ForgeAI Planner Plugin

The Planner Plugin decomposes high-level user project goals into structured planning models, analyzing functional/non-functional requirements, estimating task ordering, and submitting parallel task graphs (DAGs) to the Task Engine.

## Features
- **Goal Analysis**: Deconstructs user inputs into milestones and tasks.
- **Requirement Dependency Estimator**: Generates priority and structural dependencies between requirements.
- **Clarification engine**: Formulates clarifying questions for ambiguous inputs.
- **Task Engine mapping**: Translates task outputs into a `TaskDAG` for asynchronous orchestration.
- **Decoupled DI registry**: Exposes the `PlannerService` interface.

## Usage
```python
planner = registry.resolve(PlannerService)
plan = planner.plan_project("Build a Course Outcome Management System")
```
