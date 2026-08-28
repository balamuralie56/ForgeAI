"""
Durable workspace writer for security audits, generating Markdown, JSON, manifest, and SARIF files.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_plugins.security.models import (
    SecurityReport,
    SecurityManifest,
    SecurityFinding,
)
from forge_plugins.security.exceptions import SecurityWriteError

logger = logging.getLogger("ForgeAI.Plugins.Security.Writer")


class SecurityWorkspaceWriter:
    """
    Atomically writes security findings logs and standard SARIF reports to target workspaces.
    """

    def __init__(self, event_bus: EventBusService) -> None:
        self.event_bus = event_bus

    def write_reports(
        self,
        workspace: str,
        report: SecurityReport,
        manifest: SecurityManifest,
    ) -> None:
        """
        Writes all output audit formats to the workspace root.
        """
        workspace_path = Path(workspace)
        if not workspace_path.exists():
            raise SecurityWriteError(f"Workspace path does not exist: {workspace}")

        try:
            # 1. JSON Report
            json_report_path = workspace_path / "security_report.json"
            json_report_path.write_text(
                json.dumps(report.to_dict(), indent=4), encoding="utf-8"
            )

            # 2. Markdown Summary
            md_summary_path = workspace_path / "security_summary.md"
            md_summary_path.write_text(report.summary, encoding="utf-8")

            # 3. JSON Manifest
            manifest_path = workspace_path / "security_manifest.json"
            manifest_path.write_text(
                json.dumps(manifest.to_dict(), indent=4), encoding="utf-8"
            )

            # 4. SARIF standard file
            sarif_data = self._generate_sarif(report.findings)
            sarif_path = workspace_path / "sarif.json"
            sarif_path.write_text(json.dumps(sarif_data, indent=4), encoding="utf-8")

            logger.info(
                f"Successfully wrote security audit deliverables to {workspace}"
            )

            # Publish event
            self.event_bus.publish(
                Event(
                    event_type="security.report.generated",
                    data={
                        "project_id": report.project_id,
                        "security_score": report.security_score,
                        "findings_count": len(report.findings),
                    },
                )
            )

        except Exception as e:
            logger.error(f"Failed to write security reports: {e}", exc_info=True)
            raise SecurityWriteError(f"Failed writing security files: {e}") from e

    def _generate_sarif(self, findings: List[SecurityFinding]) -> Dict[str, Any]:
        """
        Constructs a standard SARIF v2.1.0 JSON representation from findings list.
        """
        rules_map: Dict[str, Dict[str, Any]] = {}
        results: List[Dict[str, Any]] = []

        for f in findings:
            rule_id = f.rule_id
            if rule_id not in rules_map:
                rules_map[rule_id] = {
                    "id": rule_id,
                    "name": f.title,
                    "shortDescription": {"text": f.title},
                    "fullDescription": {"text": f.description},
                    "properties": {
                        "category": f.category,
                        "severity": f.severity.value,
                        "precision": "high",
                    },
                }
                if f.cwe:
                    rules_map[rule_id]["properties"]["cwe"] = f.cwe
                if f.owasp:
                    rules_map[rule_id]["properties"]["owasp"] = f.owasp

            result = {
                "ruleId": rule_id,
                "message": {"text": f.description},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": f.file_path if f.file_path else "unknown"
                            },
                            "region": {
                                "startLine": f.line_number if f.line_number else 1
                            },
                        }
                    }
                ],
                "fingerprints": {"scanFindingFingerprint/v1": f.fingerprint},
            }
            results.append(result)

        driver = {
            "name": "ForgeAI Security Analyzer",
            "version": "1.0.0",
            "rules": list(rules_map.values()),
        }

        run = {"tool": {"driver": driver}, "results": results}

        return {
            "$schema": "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0-rtm.5.json",
            "version": "2.1.0",
            "runs": [run],
        }
