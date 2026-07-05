"""
Release Document Generator step in the documentation compilation pipeline.
"""

from ..utils.doc_pipeline import DocContext, DocPipelineStep
from ..utils.prompt_helper import load_prompt_and_generate


class ReleaseDocGenerator(DocPipelineStep):
    """
    Generates version release notes, migration directions, and upgrade checklist documents.
    """

    @property
    def name(self) -> str:
        return "Release Document Generator"

    def run(self, context: DocContext) -> None:
        docs = load_prompt_and_generate(context, "release", "release")
        context.generated_docs.extend(docs)
