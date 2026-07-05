# Planning Architecture Specification

This document serves as the frozen, high-level architectural source of truth for the Planning Layer of ForgeAI. It describes the design, communications, and boundaries of the Planner and Architect subsystems without referencing low-level implementation details.

---

## 1. Subsystem Overviews

### What is the Planner?
The Planner is the entry point of the Planning Layer. It is responsible for:
- Analyzing abstract, natural language project goals.
- Decomposing goals into structured requirements, milestones, tasks, and task dependencies.
- Identifying risks, assumptions, and formulation of clarification questions.
- Generating a directed acyclic task graph (DAG) representing the estimated execution schedule and registering it with the execution core.

### What is the Architect?
The Architect translates structured planning metadata into concrete software designs. It is responsible for:
- Mapping task directories and structural module boundaries.
- Designing API schemas, contracts, and endpoint specifications.
- Planning relational database tables, fields, and constraint references.
- Drafting Technology Decisions and Architecture Decision Records (ADRs) to document reasoning.
- Constructing system visualization diagrams.

---

## 2. Collaboration & Communication Flow

The Planner and the Architect are decoupled and interact via:
1. **Dynamic Task Core Triggering**: The Planner registers a Task graph (DAG) with the Task Engine. The first task in the graph references a design action that dynamically invokes the Architect service at runtime.
2. **Project Memory Persistence**: The Planner persists its completed plans under a metadata key in the Memory Service. The Architect retrieves this plan state as input context.
3. **Event-Driven Messaging**: Both components dispatch transactional event frames onto the Event Bus to notify observers of status updates.

---

## 3. Services Consumed

| Subsystem | Service | Purpose |
| --- | --- | --- |
| **Planner** | Model Router | Standardized LLM inference provider interface |
| | Event Bus | Broadcasts state changes to subscribers |
| | Memory Engine | Stores transient states and persistent metadata |
| | Task Engine | Registers scheduling pipelines and execution DAGs |
| **Architect** | Model Router | Standardized LLM inference provider interface |
| | Event Bus | Broadcasts state changes to subscribers |
| | Memory Engine | Stores transient states and persistent metadata |

---

## 4. Events Published

- **`planner.plan_created`**: Published immediately when a natural language goal has been processed and compiled into a structured Project Plan.
- **`architect.spec_created`**: Published when the software design specification, database schemas, and ADRs are generated.

---

## 5. Produced Models

### Planner Outputs
- **Project Goal**: The targeted goal and scope.
- **Requirement Spec**: Prioritized list of functional and non-functional requirements.
- **Clarification List**: Unresolved queries and default assumptions.
- **Milestone List**: Sequential phases of development.
- **Task List**: Individual work units with duration estimates and parent references.
- **Project Plan**: The unified container holding the above entities.

### Architect Outputs
- **Module Spec**: Logical boundaries, purposes, and code dependencies.
- **API Spec**: Endpoint methods, payload models, and response formats.
- **Database Schema**: Relational table layout, column definitions, primary/foreign key mappings.
- **Technology Decision**: Technology stack choices and rationales.
- **Architecture Decision Record (ADR)**: Durable log of design context, decisions, and consequences.
- **Architecture Specification**: The unified container holding the directory trees, modules, database schema, ADRs, and diagrams.

---

## 6. Sibling and Downstream Dependencies

The following future implementation and validation plugins depend on the outputs of the Planning Layer:
- **Developer Plugin**: Consumes the Module Specification, API Contracts, and Database Schema to write source code files.
- **Tester Plugin**: Utilizes API Specifications and Requirement Specs to generate functional and integration tests.
- **Documentation Plugin**: Uses ADRs, Project Plans, and Architecture Specifications to produce system documentation.
- **Git Plugin**: Commits files and manages branches based on the tasks and milestones scheduled by the Planner.
- **Security Plugin**: Validates designed API schemas and library selections against safety constraints.
