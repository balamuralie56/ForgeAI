# ForgeAI Architect Plugin

The Architect Plugin maps project plans into structural software design specifications, detailing table layouts, API endpoints, module groupings, directory structures, and Architecture Decision Records (ADRs).

## Features
- **Module and Service Boundaries**: Groups components and details dependency mappings.
- **API Spec Contracts**: Outlines HTTP routes, payload schemas, and response formats.
- **Database Schema**: Establishes columns, primary keys, and foreign keys.
- **ADRs**: Tracks design context, rationale, and consequences (ADR-001, etc.).
- **Mermaid diagrams**: Auto-generates diagram contexts.

## Usage
```python
architect = registry.resolve(ArchitectService)
specification = architect.design_architecture(plan)
```
