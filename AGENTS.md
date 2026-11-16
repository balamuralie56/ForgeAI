# ForgeAI - AI Development Agent Guide

# 1. Project Overview

Project Name:
ForgeAI

Mission:
ForgeAI is a completely local, privacy-first AI Operating System for Software Engineering.

Its purpose is to autonomously:

• Plan software projects
• Design software architecture
• Develop applications
• Write tests
• Debug code
• Generate documentation
• Review pull requests
• Maintain projects over time

The system must operate locally on the user's computer and must never depend on paid cloud AI services.

ForgeAI is not a chatbot.

ForgeAI is an autonomous software engineering platform.

---

# 2. Vision

The long-term objective is to create an AI Operating System capable of replacing an entire software engineering team while remaining fully local, transparent, extensible, and open.

The final system should be capable of developing:

- Desktop Applications
- Mobile Applications
- Web Applications
- AI Systems
- Machine Learning Pipelines
- Deep Learning Systems
- IoT Projects
- Embedded Systems
- Robotics Software
- APIs
- Enterprise Applications
- Research Projects

using autonomous planning and execution.

---

# 3. Core Philosophy

ForgeAI follows these principles.

1. Local First

Everything should run locally.

No paid APIs.

No cloud inference.

No vendor lock-in.

The user owns everything.

---

2. Privacy First

No project data should leave the local machine.

All source code remains local.

No telemetry.

No analytics.

No hidden uploads.

---

3. Modular Architecture

Everything is a module.

Nothing is tightly coupled.

Every major component must be replaceable.

Plugins must communicate only through interfaces.

---

4. Extensibility

Every subsystem should support future expansion without modifying existing code.

Follow the Open/Closed Principle.

---

5. Production Quality

Every implementation must be production-ready.

Never generate:

TODO

pass

placeholder methods

dummy implementations

mock business logic

unfinished code

Everything delivered should be deployable.

---

# 4. Project Architecture

The architecture is divided into independent subsystems.

Launcher

↓

Kernel

↓

Service Registry

↓

Configuration Engine

↓

Logging Engine

↓

Plugin Manager

↓

Model Router

↓

Event Bus

↓

Task Engine

↓

Memory Engine

↓

AI Plugins

The dependency direction must never be violated.

Higher layers depend only on interfaces.

Never import implementation classes directly.

---

# 5. Current Project Status

Current Version

v0.9.5

Completed

✔ Core Runtime — Kernel, Configuration, Logging, Event Bus, Memory, Plugin Manager, Task Engine (DAG scheduler/retry), History Engine (per-run workflow and report history, shown in the React UI sidebar), Model Router (Ollama + OpenAI-compatible providers), Workflow Orchestrator (state machine, stage scheduler, crash recovery)

✔ All 8 AI Plugins — Planner, Architect, Developer, Tester, Documentation, Git, Security, Reviewer (each with service + models + components and a dedicated test suite)

✔ FastAPI Backend (`forge_api`) — REST + WebSocket API exposing diagnostics, workflow creation/status, file listing, and plugin reports

✔ React Frontend (`forge_frontend`) — multi-tab workbench consuming the real API/WebSocket stream

✔ Unit Tests — 363 tests across `forge_tests`, 100% passing

✔ Git Repository / GitHub Repository / Documentation / Changelog

Known, intentional gap

- Reviewer Plugin's Liskov Substitution (L) check is explicitly unimplemented — it is documented in `forge_docs/ROADMAP.md` as needing cross-class contract analysis the current rule interface can't do. This is a deliberate scope boundary, not a stub.

Remaining roadmap item

- v1.0.0 "Production Release" — polishing the above into a shippable local platform. No CLI yet for triggering workflows outside the API/frontend; "Sprint 6+" items (distributed execution, model collaboration, self-improvement, plugin marketplace) are not started.

Completed work must not be rewritten unless fixing an actual defect.

---

# 6. Sprint Roadmap

Sprint 1 — Completed

Configuration

Logging

Launcher

Workspace

Sprint 2 — Completed

Kernel

Service Registry

Lifecycle Manager

Plugin Manager

Model Router

Sprint 3 — Completed

Event Bus

Task Engine

Memory Engine

Sprint 4 — Completed

Planner Plugin

Architect Plugin

Sprint 5 — Completed

Developer Plugin

Tester Plugin

Documentation Plugin

Git Plugin

Security Plugin

Sprint 6-11 — Completed (beyond the original sketch above)

Workflow Orchestrator (state machine, scheduler, crash recovery)

Reviewer Plugin (code smells + SOLID scoring; Liskov check intentionally out of scope — see Section 5)

FastAPI Backend (`forge_api`)

React Frontend (`forge_frontend`)

Remaining — Not Started

v1.0.0 Production Release (the only item still planned)

Optimization

Distributed Execution

Model Collaboration

Self Improvement

Plugin Marketplace

---

# 7. Engineering Standards

Python Version

Python 3.13+

Every file must include

Type hints

Google-style docstrings

PEP-8 compliance

Black formatting

Ruff compliance

Mypy compatibility

No wildcard imports

No circular imports

Every public method documented.

---

# 8. Software Design Principles

Dependency Injection

Composition over Inheritance

Single Responsibility Principle

Interface Segregation Principle

Open Closed Principle

Immutable configuration objects

Pure functions whenever possible

No global mutable state

Loose coupling

High cohesion

---

# 9. Testing Requirements

Every module must include

Unit Tests

Integration Tests (when applicable)

Failure Tests

Edge Case Tests

Concurrency Tests (if async)

Regression Tests

The project should never accept code without automated tests.

---

# 10. Pull Request Requirements

Every module must be delivered as a complete Pull Request.

Each PR must include

Technical Design Document

Architecture Diagram (if needed)

Production Implementation

Unit Tests

Integration Tests

README

Directory Structure

Example Usage

Configuration Updates

Changelog Entry

Merge Checklist

Never stop after producing only documentation.

Never stop after producing only code.

Deliver the complete feature.

---

# 11. Repository Rules

Do not rewrite previously approved architecture.

Do not remove existing features.

Backward compatibility is mandatory.

Do not duplicate existing functionality.

Always inspect the repository before writing code.

Reuse existing implementations.

Keep commits focused.

Never mix unrelated changes.

---

# 12. Performance Requirements

Launcher boot

< 1 second

Configuration load

< 100 ms

Logging

Non-blocking

Thread-safe

Memory usage while idle

Minimal

Graceful shutdown

Required

---

# 13. Error Handling

Catch specific exceptions.

Never silently ignore errors.

Never use bare except clauses.

Every failure should generate structured log entries.

Critical failures should terminate gracefully.

---

# 14. AI Model Strategy

ForgeAI must support multiple providers.

Never hardcode one provider.

Supported providers should eventually include

Ollama

llama.cpp

vLLM

LM Studio

OpenAI-compatible APIs

Future local inference engines

All providers must implement a common interface.

---

# 15. Free Software Policy

This project must remain buildable using free software.

Current stack

Python

VS Code

Git

GitHub (private repository)

Ollama

Qwen Coder

DeepSeek Coder

Llama

Docker Community Edition

WSL

SQLite

FAISS

Sentence Transformers

Pytest

Black

Ruff

Mypy

GitHub Actions

No paid software should be required.

Optional services such as Google Colab, Lightning AI, or cloud storage may be used only for temporary experimentation, backups, or training support. ForgeAI itself must remain fully functional without them.

---

# 16. Development Workflow

Understand the repository.

Read the existing architecture.

Read the documentation.

Understand dependencies.

Design the solution.

Implement production code.

Write tests.

Run tests.

Update documentation.

Update changelog.

Prepare Pull Request.

Never skip steps.

---

# 17. Coding Rules

Never use placeholders.

Never leave incomplete methods.

Never generate dead code.

Never create duplicate classes.

Never modify unrelated files.

Never ignore failing tests.

Never break previous functionality.

---

# 18. Communication Style

Do not explain basic programming concepts.

Assume the repository owner is an experienced software engineer.

When implementing features

Be concise.

Be technically accurate.

Focus on engineering quality.

Do not generate unnecessary text.

Deliver production-quality artifacts.

---

# 19. Long-Term Goal

The completed ForgeAI platform should function as a local autonomous software engineering operating system capable of planning, designing, developing, testing, documenting, deploying, maintaining, and improving software projects using only local open-source AI models.

Every implementation decision should move the project toward this objective.