"""
Documentation Summary Generator step in the documentation compilation pipeline.
"""

from typing import Dict
from ..utils.doc_pipeline import DocContext, DocPipelineStep
from ..models import GeneratedDocFile


class DocSummaryGenerator(DocPipelineStep):
    """
    Compiles a central markdown index dashboard detailing all generated files.
    """

    @property
    def name(self) -> str:
        return "Doc Summary Generator"

    def run(self, context: DocContext) -> None:
        stats: Dict[str, int] = {}
        for doc in context.generated_docs:
            stats[doc.category] = stats.get(doc.category, 0) + 1

        total_docs = len(context.generated_docs)

        markdown = []
        markdown.append(
            f"# Documentation Dashboard: {context.architecture.project_id}\n"
        )
        markdown.append("## Executive Summary")
        markdown.append(
            "Autonomous technical documentation package built successfully."
        )
        markdown.append(f"- **Total Documents Compiled**: {total_docs}\n")

        markdown.append("### Statistics by Category")
        for cat, count in sorted(stats.items()):
            markdown.append(f"- **{cat.capitalize()} Documents**: {count}")
        markdown.append("")

        markdown.append("## Generated Documentation Registry")
        markdown.append("| File Path | Document Category | Size (Bytes) |")
        markdown.append("| --- | --- | --- |")
        for doc in context.generated_docs:
            size = len(doc.content.encode("utf-8"))
            markdown.append(f"| `{doc.path}` | {doc.category} | {size} |")
        markdown.append("")

        markdown.append("---\n*Documentation generated autonomously by ForgeAI.*")

        report_content = "\n".join(markdown)
        summary_file = GeneratedDocFile(
            path="docs/INDEX.md",
            content=report_content,
            category="summary",
        )
        context.generated_docs.append(summary_file)
