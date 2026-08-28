# ForgeAI Master Roadmap

This document serves as the project's north star, outlining the historical milestones, current release state, and upcoming sprint phases leading to the production release of ForgeAI.

```
                  ForgeAI
                     │
      ┌──────────────┴──────────────┐
      │                             │
   Core Runtime                 AI Plugins
      │                             │
├─ Kernel                    ├─ Planner
├─ Configuration             ├─ Architect
├─ Logging                   ├─ Developer
├─ Memory                    ├─ Tester
├─ Event Bus                 ├─ Documentation
├─ Task Engine               ├─ (Git)
├─ Model Router              ├─ (Security)
└─ Plugin Manager            └─ (Reviewer)
```

---

## Release Timeline

### [v0.1.0] — Foundation
- **Focus**: Config and Logging Engines.
- **Status**: Completed.
- **Deliverables**: Strict immutable dataclass configuration and non-blocking, thread-safe logging.

### [v0.2.0] — Runtime Core
- **Focus**: Kernel and Lifecycles.
- **Status**: Completed.
- **Deliverables**: Modular `ForgeAIKernel`, dynamic plugin managers, and service registry.

### [v0.3.1] — Execution Core
- **Focus**: Memory and Tasks.
- **Status**: Completed.
- **Deliverables**: Event bus, SQLite memory registers, task engine graph orchestrators, and diagnostics.

### [v0.4.0] — Planning Intelligence
- **Focus**: Planner and Architect.
- **Status**: Completed.
- **Deliverables**: Goal deconstructors, UML model mapping, and architecture ADR synthesis.

### [v0.5.0] — Developer Plugin
- **Focus**: Implementation Pipeline.
- **Status**: Completed.
- **Deliverables**: Deconstructed component-specific code generation (API, DB, frontend, backend).

### [v0.6.0] — Tester Plugin
- **Focus**: Quality Verification.
- **Status**: Completed.
- **Deliverables**: Run-time validation, pytest execution runners, coverage analyzers, merge logic, and manifests.

### [v0.7.0] — Technical Writer AI
- **Focus**: Documentation Plugin.
- **Status**: Completed.
- **Deliverables**: Complete AI-powered documentation generator — project docs (README, CONTRIBUTING, LICENSE, CHANGELOG), developer guides (installation, config, troubleshooting), API references, Mermaid architecture diagrams, user manuals, and release notes. Atomic workspace writes with rollback, manifest tracking, and 93% test coverage.

### [v0.8.0] — Git Integration
- **Focus**: Git Plugin.
- **Status**: Completed.
- **Deliverables**: Full local Git automation (branch, commit, semver, tag, changelog), optional GitHub PR creation via PyGithub (config-gated), `ci_manifest.json` output for CI/CD pipelines, LLM-enhanced commit messages (opt-in), and 30+ unit tests.

### [v0.9.0] — Workflow & Orchestration
- **Focus**: Workflow Orchestrator.
- **Status**: Completed.
- **Deliverables**: Coordinating the complete user request pipeline from Planner to Git with retries and profile defaults.

### [v0.9.5] — Platform Assurance
- **Focus**: Security & Reviewer Plugins.
- **Status**: In Progress — Security Plugin completed; Reviewer Plugin not started.
- **Deliverables**: Secret scanning, AST-based vulnerability checks (eval/exec/shell/pickle/weak-crypto/SQL injection/temp files), dependency CVE checks, copyleft license scanning, SARIF export, and release-blocking quality gates — all shipped and tested (`forge_plugins/security/`, 238 tests). Code smell reviews and SOLID compliance scoring (the Reviewer Plugin) remain unbuilt.

### [v1.0.0] — ForgeAI Release
- **Focus**: Production Release.
- **Status**: Planned.
- **Deliverables**: Fully local, autonomous software engineering platform.
