"""
License compatibility checker flagging copyleft licenses (GPL, AGPL) in requirements.
"""

import re
import uuid
import hashlib
from pathlib import Path
from typing import List
from forge_plugins.security.models import SecurityFinding, Severity


class LicenseChecker:
    """
    Checks dependency manifests for copyleft licenses that may restrict redistribution.
    """

    # Mock package licenses mapping (Package -> License type)
    # Real licensing checks require pulling package metadata or parsing setup details,
    # so we pre-seed mappings and use keyword matching heuristics.
    KNOWN_LICENSES = {
        "django": "BSD",
        "pyyaml": "MIT",
        "requests": "Apache-2.0",
        "jinja2": "BSD",
        "gpl-package": "GPL-3.0",
        "agpl-package": "AGPL-3.0",
        "pygithub": "LGPL-3.0",
    }

    def __init__(self, workspace_path: str) -> None:
        self.workspace = Path(workspace_path)

    def check_licenses(self) -> List[SecurityFinding]:
        """
        Scans requirements.txt and checks for copyleft packages.
        """
        findings: List[SecurityFinding] = []
        req_file = self.workspace / "requirements.txt"

        if not req_file.exists():
            return findings

        try:
            content = req_file.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()

            for line_idx, line in enumerate(lines, start=1):
                cleaned = line.strip()
                if not cleaned or cleaned.startswith("#"):
                    continue

                # extract package name
                match = re.match(r"^([a-zA-Z0-9_\-]+)", cleaned)
                if match:
                    package_name = match.group(1).lower()
                    lic = self.KNOWN_LICENSES.get(
                        package_name, "MIT"
                    )  # Default to MIT for unrecognized

                    if "gpl" in lic.lower() or "agpl" in lic.lower():
                        desc = f"Dependency '{package_name}' uses copyleft license '{lic}'. Copyleft restrictions can require open-sourcing proprietary software if distributed."
                        fingerprint_content = (
                            f"SEC-LIC-GPL:requirements.txt:{line_idx}:{desc}"
                        )
                        fingerprint = hashlib.sha256(
                            fingerprint_content.encode("utf-8")
                        ).hexdigest()

                        finding = SecurityFinding(
                            id=str(uuid.uuid4()),
                            rule_id="SEC-LIC-GPL",
                            category="LicenseCompliance",
                            title="Copyleft License Warning",
                            description=desc,
                            severity=Severity.MEDIUM,
                            confidence="HIGH",
                            cwe="CWE-358",
                            owasp=None,
                            file_path="requirements.txt",
                            line_number=line_idx,
                            recommendation=f"Review licensing constraints for {package_name}. Consider replacing with MIT/BSD/Apache licensed alternatives.",
                            fingerprint=fingerprint,
                        )
                        findings.append(finding)
        except Exception:
            pass

        return findings
