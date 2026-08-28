"""
Secret scanner scanning workspace files for credentials, private keys, and API tokens.
"""

import re
import uuid
import hashlib
from pathlib import Path
from typing import List
from forge_plugins.security.models import SecurityFinding, Severity


class SecretScanner:
    """
    Regex-based scanner detecting hardcoded secrets and keys in text assets.
    """

    # Dictionary of regex rules: Rule ID -> (Title, Pattern, Severity, Description)
    SECRET_RULES = {
        "SEC-KEY-PEM": (
            "Private Key Exposure",
            re.compile(r"-----BEGIN\s+.*PRIVATE\s+KEY-----"),
            Severity.CRITICAL,
            "Detected embedded PEM private key block. Leaking private keys compromises cryptographic exchanges.",
        ),
        "SEC-KEY-AWS": (
            "AWS Access Token Exposure",
            re.compile(
                r"(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"
            ),
            Severity.CRITICAL,
            "Detected hardcoded AWS access key ID. Credentials should be provisioned via IAM configuration.",
        ),
        "SEC-KEY-GENERIC": (
            "Generic API Token Heuristic",
            re.compile(
                r"(api_key|apikey|secret_key|jwt_secret|bearer_token|auth_token)\s*=\s*['\"][a-zA-Z0-9_\-]{20,}['\"]",
                re.IGNORECASE,
            ),
            Severity.HIGH,
            "Detected potential hardcoded API/Secret key credentials.",
        ),
    }

    def __init__(self, workspace_path: str) -> None:
        """Initializes the scanner with workspace path."""
        self.workspace = Path(workspace_path)

    def scan_file(self, relative_path: str) -> List[SecurityFinding]:
        """
        Scans a file line-by-line for secret keys matching patterns.
        """
        findings: List[SecurityFinding] = []
        file_path = self.workspace / relative_path

        if not file_path.exists() or file_path.is_dir():
            return findings

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()

            for line_idx, line in enumerate(lines, start=1):
                # Run each secret regex pattern
                for rule_id, (
                    title,
                    pattern,
                    severity,
                    desc,
                ) in self.SECRET_RULES.items():
                    if pattern.search(line):
                        fingerprint_content = (
                            f"{rule_id}:{relative_path}:{line_idx}:{desc}"
                        )
                        fingerprint = hashlib.sha256(
                            fingerprint_content.encode("utf-8")
                        ).hexdigest()

                        finding = SecurityFinding(
                            id=str(uuid.uuid4()),
                            rule_id=rule_id,
                            category="Credentials",
                            title=title,
                            description=desc,
                            severity=severity,
                            confidence="HIGH",
                            cwe="CWE-798",
                            owasp="A07:2021-Identification and Authentication Failures",
                            file_path=relative_path,
                            line_number=line_idx,
                            recommendation="Move sensitive credentials to a git-ignored environment file.",
                            fingerprint=fingerprint,
                        )
                        findings.append(finding)
        except Exception:
            # Skip unreadable or corrupted files gracefully
            pass

        return findings
