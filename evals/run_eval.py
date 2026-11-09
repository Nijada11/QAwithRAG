"""Evaluate retrieval and answers against evals/questions.jsonl.

    python -m evals.run_eval check                   # every evidence phrase exists in the corpus
    python -m evals.run_eval retrieval               # compare retrieval setups (free, no LLM)
    python -m evals.run_eval answers --label baseline --chunk-words 600 --retrieval vector
    python -m evals.run_eval rejudge reports/answers_baseline.json   # judge only, no new answers

Each question has a reference answer and an evidence phrase copied from the document that
answers it. A retrieved chunk counts as "the right chunk" when it contains the evidence
phrase. That works for any chunk size, unlike comparing chunk ids. Six questions have no
answer in the corpus; for those the right behaviour is "I don't know".
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from src.config import ROOT, RagConfig

QUESTIONS = ROOT / "evals" / "questions.jsonl"
REPORTS = ROOT / "reports"
JUDGE_MODEL = "claude-sonnet-5-5"


def normalize(text: str) -> str:
    text = text.lower().replace("‑", "-").replace("–", "-").replace("—", "-")
    text = text.replace("’", "'").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def contains_evidence(text: str, evidence: str | list[str]) -> bool:
    """True if the text holds the evidence phrase (or any of them, when a fact is stated twice)."""
    phrases = [evidence] if isinstance(evidence, str) else evidence
    return any(normalize(phrase) in normalize(text) for phrase in phrases)


def load_questions() -> list[dict]:
    with open(QUESTIONS, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --- check ---------------------------------------------------------------------------------


def cmd_check() -> None:
    from src.ingest import load_document

    texts = {}
    for line in open(ROOT / "data" / "manifest.jsonl", encoding="utf-8"):
        entry = json.loads(line)
        path = ROOT / "data" / entry["file"]
        doc = load_document(path.read_bytes(), path.name, entry["doc_id"])
        texts[entry["doc_id"]] = "\n\n".join(b.text for b in doc.blocks)
    problems = 0
    for q in load_questions():
        if q["evidence"] is None:
            continue
        phrases = [q["evidence"]] if isinstance(q["evidence"], str) else q["evidence"]
        for phrase in phrases:
            if not any(contains_evidence(t, phrase) for t in texts.values()):
                problems += 1
                print(f"{q['id']}: evidence not found: {phrase!r}")
        docs = [d for d, t in texts.items() if contains_evidence(t, q["evidence"])]
        if len(docs) > 1:
            print(f"{q['id']}: evidence in {len(docs)} documents (fine): {', '.join(docs)}")
    print("all evidence found" if not problems else f"{problems} problems")
    raise SystemExit(1 if problems else 0)


# --- retrieval -----------------------------------------------------------------------------

RETRIEVAL_SETUPS = [
    # (label, chunk_words, overlap_words, retrieval mode)
    ("600w vector (baseline)", 600, 100, "vector"),
    ("600w keyword (BM25)", 600, 100, "keyword"),
    ("600w hybrid", 600, 100, "hybrid"),
    ("600w hybrid + rerank", 600, 100, "hybrid+rerank"),
    ("250w vector", 250, 50, "vector"),
    ("250w keyword (BM25)", 250, 50, "keyword"),
    ("250w hybrid", 250, 50, "hybrid"),
    ("250w hybrid + rerank", 250, 50, "hybrid+rerank"),
]


def retrieval_metrics(rag, questions: list[dict], k: int = 5) -> dict:
    ranks = []
    latencies = []
    for q in questions:
        started = time.perf_counter()
        hits = rag.index.search(q["question"], k, rag.config.retrieval)
        latencies.append((time.perf_counter() - started) * 1000)
        rank = next(
            (i for i, h in enumerate(hits, 1) if contains_evidence(h.chunk.text, q["evidence"])),
            None,
        )
        ranks.append(rank)
    n = len(questions)
    return {
        "hit@1": sum(r == 1 for r in ranks if r) / n,
        "hit@3": sum(r <= 3 for r in ranks if r) / n,
        "hit@5": sum(r <= 5 for r in ranks if r) / n,
        "mrr@5": sum(1 / r for r in ranks if r) / n,
        "p50_ms": statistics.median(latencies),
        "misses": [q["id"] for q, r in zip(questions, ranks, strict=True) if r is None],
    }


def cmd_retrieval(args) -> None:
    from src.rag import RAG
    from src.store import CrossEncoderReranker, Index, SentenceTransformerEmbedder

    questions = [q for q in load_questions() if q["evidence"]]
    base = RagConfig.from_env().with_(usage_log=None)
    embedder = SentenceTransformerEmbedder(base.embed_model)
    reranker = CrossEncoderReranker(base.rerank_model)
    rows = []
    for label, words, overlap, mode in RETRIEVAL_SETUPS:
        config = base.with_(chunk_words=words, overlap_words=overlap, retrieval=mode)
        index = Index(str(config.index_dir), config.collection, embedder, reranker)
        if index.count() == 0:
            print(
                f"skipping {label}: build it with  python -m src.cli build "
                f"--chunk-words {words} --overlap-words {overlap}"
            )
            continue
        metrics = retrieval_metrics(RAG(config, index=index), questions)
        rows.append({"setup": label, **metrics})
        print(
            f"{label:24} hit@1 {metrics['hit@1']:.0%}  hit@5 {metrics['hit@5']:.0%}  "
            f"MRR {metrics['mrr@5']:.2f}  misses {metrics['misses']}"
        )

    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "retrieval.json").write_text(json.dumps(rows, indent=2))
    lines = [
        f"# Retrieval: {len(questions)} answerable questions, top 5",
        "",
        "| Setup | Hit@1 | Hit@3 | Hit@5 | MRR@5 | p50 latency |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['setup']} | {r['hit@1']:.0%} | {r['hit@3']:.0%} | {r['hit@5']:.0%} "
            f"| {r['mrr@5']:.2f} | {r['p50_ms']:.0f} ms |"
        )
    (REPORTS / "retrieval.md").write_text("\n".join(lines) + "\n")
    print(f"\nwrote {REPORTS / 'retrieval.md'}")


# --- answers -------------------------------------------------------------------------------

JUDGE_SYSTEM = """\
You grade answers from an IT helpdesk assistant against a reference answer.

- "correct": the answer states the key fact(s) of the reference and says nothing that \
contradicts it. Extra correct detail is fine.
- "partial": the answer has some of the key facts but misses an essential one, or hedges \
where the reference is definite.
- "incorrect": the answer is wrong, contradicts the reference, or says it doesn't know.

Separately, decide "grounded": true if every factual claim in the answer is supported by the \
quoted source passages it cites, false if any claim is missing from or contradicted by them. \
Judge grounding only against the passages, not against the reference."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "verdict": {"type": "string", "enum": ["correct", "partial", "incorrect"]},
        "grounded": {"type": "boolean"},
    },
    "required": ["reasoning", "verdict", "grounded"],
    "additionalProperties": False,
}


def judge(client, question: str, reference: str, answer: str, sources: list[dict]) -> tuple[dict, dict]:
    # Grouped by the source number the answer's [n] markers use; one source can hold
    # several quoted passages.
    passages = (
        "\n\n".join(f'<source n="{s["n"]}">\n' + "\n\n".join(s["quotes"]) + "\n</source>" for s in sources)
        or "(none)"
    )
    response = client.beta.messages.create(
        model=JUDGE_MODEL,
        max_tokens=4000,
        system=JUDGE_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Question: {question}\n\nReference answer: {reference}\n\n"
                f"Assistant's answer:\n{answer}\n\nThe passages each [n] marker cites:\n{passages}",
            }
        ],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
        # Server-side fallback to another model if a safety classifier declines the request.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        return {"verdict": "error", "reasoning": "judge refused"}, {}
    text = next(b.text for b in response.content if b.type == "text")
    u = response.usage
    return json.loads(text), {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens}


def cmd_answers(args) -> None:

    from src.rag import RAG

    config = RagConfig.from_env().with_(
        chunk_words=args.chunk_words,
        overlap_words=args.overlap_words,
        retrieval=args.retrieval,
        usage_log=None,
    )
    rag = RAG(config)
    if rag.index.count() == 0:
        raise SystemExit(f"collection {config.collection} is empty; run python -m src.cli build first")
    questions = load_questions()
    if args.limit:
        questions = questions[: args.limit]

    # Sequential, so latency numbers aren't distorted by parallel requests.
    results = []
    for q in questions:
        answer = rag.ask(q["question"])
        quotes = " ".join(quote for s in answer.sources for quote in s.quotes)
        retrieved_text = (
            " ".join(rag.index.collection.get(ids=answer.retrieved)["documents"]) if answer.retrieved else ""
        )
        results.append(
            {
                **q,
                "response": answer.answer,
                "answered": answer.answered,
                "sources": [asdict(s) for s in answer.sources],
                "retrieved": answer.retrieved,
                "retrieved_evidence": bool(q["evidence"])
                and contains_evidence(retrieved_text, q["evidence"]),
                "cited_evidence": bool(q["evidence"]) and contains_evidence(quotes, q["evidence"]),
                "input_tokens": answer.input_tokens,
                "output_tokens": answer.output_tokens,
                "cost_usd": answer.cost_usd,
                "retrieval_ms": answer.retrieval_ms,
                "llm_ms": answer.llm_ms,
                "total_ms": answer.total_ms,
            }
        )
        print(f"{q['id']} {'answered' if answer.answered else 'IDK':8} {answer.total_ms / 1000:5.1f}s")

    write_report(judge_all(results), asdict(config), args.label)


def judge_all(results: list[dict]) -> tuple[list[dict], dict]:
    import anthropic

    client = anthropic.Anthropic()
    to_judge = [r for r in results if r["evidence"] and r["answered"]]
    with ThreadPoolExecutor(max_workers=4) as pool:
        verdicts = list(
            pool.map(
                lambda r: judge(client, r["question"], r["answer"], r["response"], r["sources"]), to_judge
            )
        )
    judge_tokens = {"input_tokens": 0, "output_tokens": 0}
    for r, (verdict, usage) in zip(to_judge, verdicts, strict=True):
        r["verdict"], r["judge_reasoning"] = verdict["verdict"], verdict["reasoning"]
        r["grounded"] = verdict.get("grounded")
        for key in judge_tokens:
            judge_tokens[key] += usage.get(key, 0)
    for r in results:
        if not r["evidence"]:
            r["verdict"] = "correct" if not r["answered"] else "incorrect"
        elif not r["answered"]:
            r["verdict"], r["judge_reasoning"] = "incorrect", "said it doesn't know (false refusal)"
    return results, judge_tokens


def write_report(judged: tuple[list[dict], dict], config: dict, label: str) -> None:
    results, judge_tokens = judged
    summary = summarize(results, config, label)
    summary["judge_tokens"] = judge_tokens
    REPORTS.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    (REPORTS / f"answers_{slug}.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False)
    )
    (REPORTS / f"answers_{slug}.md").write_text(render(summary, results))
    print(render(summary, results).split("## Per question")[0])


def cmd_rejudge(args) -> None:
    """Re-run only the judge on a saved report (after changing the judge, not the pipeline)."""
    saved = json.loads(Path(args.report).read_text())
    write_report(judge_all(saved["results"]), saved["summary"]["config"], saved["summary"]["label"])


def summarize(results: list[dict], config: dict, label: str) -> dict:
    answerable = [r for r in results if r["evidence"]]
    unanswerable = [r for r in results if not r["evidence"]]
    latencies = sorted(r["total_ms"] for r in results)
    cost = [r["cost_usd"] for r in results]

    def share(rows, pred):
        return sum(map(pred, rows)) / len(rows) if rows else 0.0

    return {
        "label": label,
        "config": {k: str(v) for k, v in config.items()},
        "questions": len(results),
        "answerable": len(answerable),
        "correct": share(answerable, lambda r: r["verdict"] == "correct"),
        "correct_or_partial": share(answerable, lambda r: r["verdict"] in ("correct", "partial")),
        "false_refusals": share(answerable, lambda r: not r["answered"]),
        "cited_evidence": share(answerable, lambda r: r["cited_evidence"]),
        "retrieved_evidence": share(answerable, lambda r: r["retrieved_evidence"]),
        # Of the answers given, how many make only claims their cited passages support.
        "grounded": share([r for r in answerable if r["answered"]], lambda r: bool(r.get("grounded"))),
        "idk_when_unanswerable": share(unanswerable, lambda r: not r["answered"]),
        "avg_input_tokens": statistics.mean(r["input_tokens"] for r in results),
        "avg_output_tokens": statistics.mean(r["output_tokens"] for r in results),
        "cost_per_1000_usd": 1000 * statistics.mean(cost),
        "p50_ms": statistics.median(latencies),
        "p95_ms": latencies[min(len(latencies) - 1, round(0.95 * (len(latencies) - 1)))],
        "avg_retrieval_ms": statistics.mean(r["retrieval_ms"] for r in results),
        "avg_llm_ms": statistics.mean(r["llm_ms"] for r in results),
    }


def render(s: dict, results: list[dict]) -> str:
    lines = [
        f"# Answers: {s['label']}",
        "",
        f"Chunks {s['config']['chunk_words']} words, retrieval `{s['config']['retrieval']}`, "
        f"model `{s['config']['llm_model']}`, judge `{JUDGE_MODEL}`.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Correct (of {s['answerable']} answerable) | {s['correct']:.0%} |",
        f"| Correct or partial | {s['correct_or_partial']:.0%} |",
        f"| Evidence passage retrieved (top {s['config']['top_k']}) | {s['retrieved_evidence']:.0%} |",
        f"| Evidence passage cited (exact phrase) | {s['cited_evidence']:.0%} |",
        f"| Answers grounded in their citations | {s['grounded']:.0%} |",
        f'| False "I don\'t know" | {s["false_refusals"]:.0%} |',
        f'| "I don\'t know" on unanswerable ({s["questions"] - s["answerable"]}) '
        f"| {s['idk_when_unanswerable']:.0%} |",
        f"| Avg tokens in / out | {s['avg_input_tokens']:.0f} / {s['avg_output_tokens']:.0f} |",
        f"| Cost per 1,000 questions | ${s['cost_per_1000_usd']:.2f} |",
        f"| Latency p50 / p95 | {s['p50_ms'] / 1000:.1f} s / {s['p95_ms'] / 1000:.1f} s |",
        f"| Avg retrieval / LLM time | {s['avg_retrieval_ms']:.0f} ms / {s['avg_llm_ms'] / 1000:.1f} s |",
        "",
        "## Per question",
        "",
        "| id | verdict | cited evidence | question |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['id']} | {r['verdict']} | {'yes' if r['cited_evidence'] else '-'} | {r['question']} |"
        )
    lines.append("")
    for r in results:
        if r["verdict"] != "correct":
            lines += [
                f"### {r['id']}: {r['verdict']}",
                f"**Q:** {r['question']}  ",
                f"**Reference:** {r['answer']}  ",
                f"**Judge:** {r.get('judge_reasoning', '')}",
                "",
                "> " + r["response"].replace("\n", "\n> "),
                "",
            ]
    return "\n".join(lines) + "\n"


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("retrieval")
    answers = sub.add_parser("answers")
    answers.add_argument("--label", required=True)
    answers.add_argument("--chunk-words", type=int, default=600)
    answers.add_argument("--overlap-words", type=int, default=100)
    answers.add_argument("--retrieval", default="vector")
    answers.add_argument("--limit", type=int, help="only the first N questions (smoke test)")
    rejudge = sub.add_parser("rejudge")
    rejudge.add_argument("report", help="a reports/answers_*.json file")
    args = parser.parse_args()
    {
        "check": lambda: cmd_check(),
        "retrieval": lambda: cmd_retrieval(args),
        "answers": lambda: cmd_answers(args),
        "rejudge": lambda: cmd_rejudge(args),
    }[args.command]()


if __name__ == "__main__":
    main()
