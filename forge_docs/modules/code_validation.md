# Code Validation (Developer Plugin)

The Developer Plugin statically validates every file it generates and reports an honest status, instead of reporting `SUCCESS` whenever files were written.

## Why it exists
A real `BUILD_ONLY` run on `qwen2.5-coder:3b` reported `SUCCESS`, yet its root package could not even be imported: relative imports in top-level scripts, a `from .adrs import ...` of a module that was never generated, and `JSONResponse` used without being imported. `BUILD_ONLY` has no Tester stage, so nothing caught it.

## Safety
Nothing generated is executed. Every check works on file text (Python's `ast`, `json`, `tomllib`, `tokenize`), so validating untrusted model output cannot run it. The trade-off: runtime-only bugs (wrong logic, a `KeyError`, an invalid framework argument) are not caught. The Tester stage of `FULL_ENGINEERING` is what executes code.

## Checks
| Check | Severity | Catches |
|---|---|---|
| `syntax` | error | Python that does not parse (reported with line) |
| `json`, `toml` | error | `.json` / `.toml` files that do not parse |
| `import` | error | Relative imports in top-level modules; relative imports climbing above the top package or to modules that were never generated; imports of missing local submodules; `from x import name` where no candidate module defines `name` |
| `undefined-name` | error | Names read but bound nowhere in the module (guaranteed `NameError` if reached) |
| `dependency` | warning | Third-party imports not declared in `requirements*.txt` / `pyproject.toml` (PEP 503 name normalization, plus common import→distribution aliases such as `yaml`→`PyYAML`) |
| `placeholder` | warning | `TODO` / `FIXME` / "dummy" / "placeholder" / "stub" comments; functions whose body is only `pass`, `...` or `raise NotImplementedError` (abstract methods, overloads and Protocol members excluded) |
| `duplicate` | warning | The same path generated twice (the last version wins), or two modules with identical content |

### Avoiding false positives
- **Absolute imports** resolve against every layout the project could be launched with: the importing script's directory (`python pkg/main.py`), the project root (`python -m`), and `src/`. An import is reported only if it fails under all of them.
- **Name checks** are scope-insensitive: a name bound anywhere in the module counts as defined, so anything reported is undefined everywhere.
- Modules with a star import or a module-level `__getattr__` are not checked for missing names, and imports guarded by `try: ... except ImportError:` are skipped.

## Status
`ImplementationReport.status` is derived from the result:

| Status | Meaning |
|---|---|
| `SUCCESS` | No issues |
| `SUCCESS_WITH_WARNINGS` | Warnings only; the code should import and run |
| `VALIDATION_FAILED` | At least one error; the code will fail when imported or run |

Validation never stops the workflow and never prevents files from being written, so the output can still be inspected and fixed. Reports created before this feature have `validation: null` and keep their original status.

## Where results appear
- `ImplementationReport.validation` (`passed`, `checked_files`, `error_count`, `warning_count`, `issues[]`), stored in project memory and in each run's history.
- A `## Code Validation` section in the generated `implementation_report.md`.
- A `developer.validated` event on the event bus (shown in the UI's Activity tab).
- A panel at the top of the UI's **Files** tab; clicking an issue opens that file.

## Usage
```python
from forge_plugins.developer.models import GeneratedFile
from forge_plugins.developer.validators import GeneratedCodeValidator

result = GeneratedCodeValidator().validate(
    [GeneratedFile(path="main.py", content="from .tasks import run\n", file_type="backend")]
)
print(result.status.value)          # VALIDATION_FAILED
for issue in result.errors:
    print(issue.path, issue.line, issue.message)
```

The pipeline runs it as `CodeValidationStep`, after the last generator and before the report generator.
