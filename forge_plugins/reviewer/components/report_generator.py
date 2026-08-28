"""
Report generator aggregating findings, computing quality/SOLID scores, and
generating a Markdown summary.
"""

import logging
from typing import List, Optional
from forge_core.model_router.service import ModelRouterService
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding, ReviewReport
from .solid_scorer import SolidScorer

logger = logging.getLogger("ForgeAI.Plugins.Reviewer.ReportGenerator")


class ReviewReportGenerator:
    """Computes code quality metrics and produces a Markdown summary."""

    @classmethod
    def calculate_quality_score(cls, findings: List[ReviewFinding]) -> float:
        """Calculates the overall 0-100 quality score from finding severities."""
        penalty = 0.0
        weights = {
            Severity.CRITICAL: 20.0,
            Severity.HIGH: 10.0,
            Severity.MEDIUM: 4.0,
            Severity.LOW: 1.5,
            Severity.INFO: 0.25,
        }
        for f in findings:
            penalty += weights.get(f.severity, 1.5)

        return round(max(0.0, 100.0 - min(100.0, penalty)), 2)

    @classmethod
    def generate_report(
        cls,
        project_id: str,
        findings: List[ReviewFinding],
        llm_review_enabled: bool,
        model_router: Optional[ModelRouterService] = None,
    ) -> ReviewReport:
        """Synthesizes the list of findings into a ReviewReport."""
        quality_score = cls.calculate_quality_score(findings)
        solid_scores = SolidScorer.score(findings)
        status = "PASSED" if quality_score >= 70.0 else "FAILED"

        recommendations = list(dict.fromkeys(f.recommendation for f in findings))
        if not recommendations:
            recommendations = ["No code quality issues detected in this pass."]

        md_lines = []
        md_lines.append("# ForgeAI Code Review Report")
        md_lines.append(f"**Project ID:** `{project_id}`")
        md_lines.append(
            f"**Quality Score:** `{quality_score}/100` | **Gate Status:** `{status}`"
        )

        md_lines.append("\n## SOLID Compliance\n")
        for principle in ("SRP", "OCP", "LSP", "ISP", "DIP"):
            value = solid_scores.get(principle)
            display = f"{value}/100" if value is not None else "not evaluated"
            md_lines.append(f"- **{principle}:** {display}")

        md_lines.append("\n## Findings by Category\n")
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
            md_lines.append("*No code quality issues detected.*")
        else:
            md_lines.append("| Rule ID | Title | Severity | Principle | File | Line |")
            md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for f in findings:
                principle_str = f.principle if f.principle else "-"
                path_str = f.file_path if f.file_path else "-"
                line_str = str(f.line_number) if f.line_number else "-"
                md_lines.append(
                    f"| {f.rule_id} | {f.title} | {f.severity.value} | {principle_str} | {path_str} | {line_str} |"
                )

        md_lines.append("\n## Key Recommendations\n")
        for rec in recommendations:
            md_lines.append(f"- {rec}")

        summary = "\n".join(md_lines)

        if llm_review_enabled and model_router and findings:
            try:
                findings_desc = []
                for f in findings:
                    findings_desc.append(
                        f"Finding: {f.title} ({f.rule_id})\n"
                        f"Principle: {f.principle or 'General'}, File: {f.file_path}:{f.line_number}\n"
                        f"Description: {f.description}\n"
                        f"Recommendation: {f.recommendation}\n"
                    )

                prompt = (
                    "You are the Senior Code Reviewer AI for ForgeAI.\n"
                    "Review the following code quality findings catalog and explain each one in a "
                    "developer-friendly way, including a short before/after refactor snippet where useful.\n\n"
                    f"Findings:\n"
                    f"{chr(10).join(findings_desc)}\n\n"
                    "Provide your final output in Markdown format."
                )
                response = model_router.generate(prompt)
                ai_explanation = response.text.strip()
                summary += f"\n\n## AI Review Notes\n\n{ai_explanation}"
            except Exception as e:
                logger.warning(f"Failed to generate LLM review explanation: {e}")

        return ReviewReport(
            project_id=project_id,
            findings=findings,
            quality_score=quality_score,
            solid_scores=solid_scores,
            status=status,
            summary=summary,
            recommendations=recommendations,
        )
