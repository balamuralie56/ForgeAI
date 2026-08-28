# ForgeAI Security Plugin (v0.10.0)

The Security Plugin acts as ForgeAI's Security Engineer, performing static analysis, secret scanning, dependency vulnerability scanning, license auditing, and OWASP-focused code checks.

## Architecture

```
forge_plugins/security/
├── rules/
│   ├── base_rule.py  # Base interface
│   └── registry.py   # Registry manager
└── components/
    ├── secret_scanner.py
    ├── vulnerability_scanner.py
    └── static_analyzer.py
```

## Features

- **Secret Scanning:** Scans credentials using regexes.
- **Dependency Audit:** Checks requirements manifests against database vulnerabilities.
- **License Checking:** Warns on copyleft packages (GPL/AGPL).
- **Static AST Checks:** Checks Python files via AST parsing rules.
- **Trend History delta:** Tracks score progression across project revisions.
- **Release Quality Gates:** Halts release checks on Git commits if violations exceed policy limits.
