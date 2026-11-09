"""Command line: build the index and ask questions.

python -m src.cli build                      # index data/ with the default settings
python -m src.cli build --chunk-words 250 --overlap-words 50
python -m src.cli ask "How long is a Temporary Access Pass valid?"
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict

from dotenv import load_dotenv

from src.config import RETRIEVAL_MODES, RagConfig


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Document Q&A with RAG")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="index the documents listed in data/manifest.jsonl")
    build.add_argument("--chunk-words", type=int)
    build.add_argument("--overlap-words", type=int)
    build.add_argument("--rebuild", action="store_true", help="drop the collection first")

    ask = sub.add_parser("ask", help="answer one question")
    ask.add_argument("question")
    ask.add_argument("--retrieval", choices=RETRIEVAL_MODES)
    ask.add_argument("--json", action="store_true")

    args = parser.parse_args()
    config = RagConfig.from_env()
    for name in ("chunk_words", "overlap_words", "retrieval"):
        if getattr(args, name, None):
            config = config.with_(**{name: getattr(args, name)})

    from src.rag import RAG

    if args.command == "build":
        rag = RAG(config)
        if args.rebuild:
            rag.index.client.delete_collection(config.collection)
            rag = RAG(config)
        started = time.perf_counter()
        n = rag.build_from_manifest()
        print(f"indexed {n} chunks into '{config.collection}' in {time.perf_counter() - started:.0f}s")
    else:
        answer = RAG(config).ask(args.question)
        if args.json:
            print(json.dumps(asdict(answer), indent=2, ensure_ascii=False))
            return
        print(answer.answer, "\n")
        for s in answer.sources:
            print(f"[{s.n}] {s.title} — {s.section}\n    {s.url}")
            for q in s.quotes:
                print(f"    > {q[:200]}")
        print(
            f"\n{answer.input_tokens} in / {answer.output_tokens} out tokens, "
            f"${answer.cost_usd:.5f}, {answer.total_ms:.0f} ms"
        )


if __name__ == "__main__":
    main()
