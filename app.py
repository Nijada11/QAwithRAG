"""Gradio demo: a question box, the answer, and clickable sources with the quoted passages.

Runs the pipeline in-process (no API server needed), which is what a Hugging Face Space
runs. On first start it builds the index from data/ if there isn't one yet.

    python app.py            # http://127.0.0.1:7860
"""

from __future__ import annotations

import html
import logging
import os

import gradio as gr
from dotenv import load_dotenv

from src.config import RagConfig
from src.llm import LLMError
from src.rag import RAG

load_dotenv()
logging.basicConfig(level=logging.INFO)

EXAMPLES = [
    "A user lost the phone with their Authenticator app. How can they get back in?",
    "How long can a Temporary Access Pass be valid?",
    "How many failed sign-ins before smart lockout locks an account?",
    "Can we switch off Microsoft's global banned password list?",
    "Is there a way to test a Conditional Access policy before enforcing it?",
    "What is the maximum mailbox size in Exchange Online?",
]

rag = RAG(RagConfig.from_env())
if rag.index.count() == 0:
    logging.info("Index is empty; building it from data/ (takes a few minutes on CPU)")
    rag.build_from_manifest()


def render_sources(sources) -> str:
    if not sources:
        return ""
    parts = ["### Sources"]
    for s in sources:
        where = s.section or (f"page {s.page}" if s.page else "")
        link = f"[{html.escape(s.title)}]({s.url})" if s.url else html.escape(s.title)
        parts.append(f"**[{s.n}]** {link}" + (f" — {html.escape(where)}" if where else ""))
        for quote in s.quotes:
            # Quote every line, so multi-line passages (lists, tables) stay inside the quote.
            parts.append("> " + quote.replace("\n", "\n> "))
    return "\n\n".join(parts)


def answer(question: str):
    question = (question or "").strip()
    if len(question) < 3:
        return "Please type a question.", "", ""
    try:
        result = rag.ask(question[:1000])
    except LLMError as e:
        return f"Sorry, the language model failed: {e}", "", ""
    stats = (
        f"{result.input_tokens:,} input / {result.output_tokens:,} output tokens · "
        f"${result.cost_usd:.4f} · retrieval {result.retrieval_ms:.0f} ms · "
        f"total {result.total_ms / 1000:.1f} s"
    )
    return result.answer, render_sources(result.sources), stats


with gr.Blocks(title="Entra ID helpdesk assistant") as demo:
    gr.Markdown(
        "# Entra ID helpdesk assistant\n"
        "Answers questions about Microsoft Entra ID sign-in, MFA, password reset, users and "
        "groups, and Conditional Access, using only "
        f"{len(rag.index.document_ids())} pages of Microsoft's public documentation. "
        "Every claim cites the passage it came from; if the documents don't cover a "
        "question, it says so."
    )
    question = gr.Textbox(label="Question", placeholder="e.g. How do I reset MFA for a user?", lines=2)
    ask = gr.Button("Ask", variant="primary")
    answer_box = gr.Markdown(label="Answer")
    sources_box = gr.Markdown()
    stats_box = gr.Markdown()
    gr.Examples(EXAMPLES, inputs=question)
    gr.Markdown(
        "<small>Not affiliated with Microsoft. Source: "
        "[MicrosoftDocs/entra-docs](https://github.com/MicrosoftDocs/entra-docs) (MIT). "
        "Answers can be wrong; check the cited page.</small>"
    )
    for trigger in (ask.click, question.submit):
        trigger(answer, inputs=question, outputs=[answer_box, sources_box, stats_box])


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=2).launch(
        server_name=os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1")
    )
