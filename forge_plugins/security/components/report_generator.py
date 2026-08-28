"""
Report generator aggregating findings, computing risk/security scores, and generating summaries.
"""

import logging
from typing import List, Optional
from forge_core.model_router.service import ModelRouterService
from forge_plugins.security.models import SecurityFinding, SecurityReport, Severity

logger = logging.getLogger("ForgeAI.Plugins.Security.ReportGenerator")


class SecurityReportGenerator:
    """
    Computes security and risk metrics and produces Markdown summary.
    """

    @classmethod
    def calculate_scores(cls, findings: List[SecurityFinding]) -> tuple[float, float]:
        """
        Calculates Risk Score and Security Score.

        Returns:
            tuple[float, float]: (risk_score, security_score)
        """
        risk_score = 0.0

        for f in findings:
            sev_val = {
                Severity.CRITICAL: 25.0,
                Severity.HIGH: 15.0,
                Severity.MEDIUM: 5.0,
                Severity.LOW: 1.0,
                Severity.INFO: 0.1,
            }.get(f.severity, 1.0)

            conf_val = {
                "HIGH": 1.0,
                "MEDIUM": 0.7,
                "LOW": 0.4,
            }.get(str(f.confidence).upper(), 1.0)

            risk_score += sev_val * conf_val

        risk_score = round(min(100.0, risk_score), 2)
        security_score = round(max(0.0, 100.0 - risk_score), 2)

        return risk_score, security_score

    @classmethod
    def generate_report(
        cls,
        project_id: str,
        findings: List[SecurityFinding],
        llm_review_enabled: bool,
        model_router: Optional[ModelRouterService] = None,
        trend_summary: str = "",
    ) -> SecurityReport:
        """
        Synthesizes the list of findings into a SecurityReport.
        """
        risk_score, security_score = cls.calculate_scores(findings)
        status = "PASSED" if security_score >= 70.0 else "FAILED"

        # Unique lists of recommendations
        recommendations = list(dict.fromkeys(f.recommendation for f in findings))
        if not recommendations:
            recommendations = [
                "No immediate security recommendations. Maintain packages updated."
            ]

        # Construct deterministic Markdown summary
        md_lines = []
        md_lines.append("# ForgeAI Security Analysis Report")
        md_lines.append(f"**Project ID:** `{project_id}`")
        md_lines.append(
            f"**Security Score:** `{security_score}/100` | **Risk Score:** `{risk_score}/100`"
        )
        md_lines.append(
            f"**Vulnerability Gate Status:** `{'PASSED' if status == 'PASSED' else 'FAILED'}`"
        )
        if trend_summary:
            md_lines.append(f"**Trend Tracker:** {trend_summary}")

        md_lines.append("\n## Findings Severity Distribution\n")
        counts = {s: 0 for s in Severity}
        for f in findings:
            counts[f.severity] += 1

        md_lines.append(f"- **Critical:** {counts[Severity.CRITICAL]}")
        md_lines.append(f"- **High:** {counts[Severity.HIGH]}")
        md_lines.append(f"- **Medium:** {counts[Severity.MEDIUM]}")
        md_lines.append(f"- **Low:** {counts[Severity.LOW]}")
        md_lines.append(f"- **Info:** {counts[Severity.INFO]}")

        md_lines.append("\n## Detailed Findings Log\n")
        if not findings:
            md_lines.append("*No security violations or vulnerabilities detected.*")
        else:
            md_lines.append(
                "| Rule ID | Title | Severity | Confidence | File | Line | CWE | OWASP |"
            )
            md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
            for f in findings:
                cwe_str = f.cwe if f.cwe else "-"
                owasp_str = f.owasp if f.owasp else "-"
                path_str = f.file_path if f.file_path else "-"
                line_str = str(f.line_number) if f.line_number else "-"
                md_lines.append(
                    f"| {f.rule_id} | {f.title} | {f.severity.value} | {f.confidence} | {path_str} | {line_str} | {cwe_str} | {owasp_str} |"
                )

        md_lines.append("\n## Key Recommendations\n")
        for rec in recommendations:
            md_lines.append(f"- {rec}")

        summary = "\n".join(md_lines)

        # Call LLM router to explain findings and format a rich remediation report when enabled
        if llm_review_enabled and model_router and findings:
            try:
                findings_desc = []
                for f in findings:
                    findings_desc.append(
                        f"Finding: {f.title} ({f.rule_id})\n"
                        f"Severity: {f.severity.value}, File: {f.file_path}:{f.line_number}\n"
                        f"Description: {f.description}\n"
                        f"Recommendation: {f.recommendation}\n"
                    )

                prompt = (
                    "You are the Senior Security Architect AI for ForgeAI.\n"
                    "Review the following security findings catalog and explain each vulnerability in a developer-friendly way.\n"
                    "Offer specific remediation code snippets showing how to rewrite the code safely.\n\n"
                    f"Findings:\n"
                    f"{chr(10).join(findings_desc)}\n\n"
                    "Provide your final output in Markdown format."
                )

                response = model_router.generate(prompt)
                ai_explanation = response.text.strip()
                summary += f"\n\n## AI Security Remediations & Explanations\n\n{ai_explanation}"
            except Exception as e:
                logger.warning(f"Failed to generate LLM explanation: {e}")

        return SecurityReport(
            project_id=project_id,
            findings=findings,
            risk_score=risk_score,
            security_score=security_score,
            status=status,
            summary=summary,
            recommendations=recommendations,
        )
