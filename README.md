# Document Q&A with RAG

**An IT helpdesk assistant that answers questions from Microsoft Entra ID documentation and cites the exact passage it used.**

It covers sign-in, MFA, self-service password reset, users and groups, and Conditional Access, using 198 pages of Microsoft's public documentation. Every claim in an answer is followed by a `[n]` marker. The matching source gives the page title, a link to learn.microsoft.com, and the quoted passages. If the documents don't contain the answer, it says "I don't know" instead of guessing.

```
question ──► hybrid retrieval (top 5) ─────────────► Claude Haiku 5.5 ──► answer + [n] markers
               ├─ vector: bge-small + Chroma        search_result blocks,   sources[]: title, URL,
               └─ keyword: BM25                     citations on            section/page, quotes
               fused with reciprocal rank fusion
```

## Results

47 test questions: 41 with a known answer and 6 the documents can't answer (e.g. "What is the maximum mailbox size in Exchange Online?"). The baseline follows the project brief (600-word chunks, vector search). The improved version is what ships.

| | Baseline<br>600-word chunks, vector | **Improved**<br>250-word chunks, hybrid |
|---|---|---|
| Right passage retrieved (top 5) | 80% | **95%** |
| Answer correct | 85% | **98%** |
| Answer correct or partly correct | 95% | 100% |
| Answer cites the right passage | 73% | **93%** |
| Every claim supported by its citations | 77% | 85% |
| "I don't know" when the answer is in the docs | 5% | 0% |
| "I don't know" when it isn't (6 questions) | 100% | 100% |
| Cost per 1,000 questions | $1.06 | **$0.70** |
| Latency p50 / p95 | 3.2 s / 5.1 s | 2.9 s / 4.4 s |

The improved setup is better on every measure and also cheaper, because smaller chunks put fewer tokens into each prompt.

### Why the brief's chunk size underperformed

The embedding model (`BAAI/bge-small-en-v1.5`) reads at most **512 tokens**. A 600-word chunk is about 740 tokens, and **80% of the 600-word chunks were longer than the model's limit**. The model silently ignores the rest, so the last third of most chunks was never searchable by meaning. At 250 words only 5% of chunks are over the limit.

### Retrieval experiments

Retrieval is cheap to evaluate (no LLM), so I compared eight setups. "Hit@5" means the passage containing the answer is among the 5 chunks sent to the model ([reports/retrieval.md](reports/retrieval.md)):

| Setup | Hit@1 | Hit@5 | MRR@5 | Latency |
|---|---|---|---|---|
| 600w vector (baseline) | 49% | 80% | 0.62 | 19 ms |
| 600w keyword (BM25) | 51% | 83% | 0.63 | 1 ms |
| 600w hybrid | 56% | 88% | 0.68 | 23 ms |
| 600w hybrid + re-ranker | 54% | 85% | 0.66 | 1159 ms |
| 250w vector | 44% | 83% | 0.59 | 19 ms |
| 250w keyword (BM25) | 39% | 78% | 0.54 | 2 ms |
| **250w hybrid** | 46% | **95%** | 0.65 | 24 ms |
| 250w hybrid + re-ranker | 49% | 80% | 0.61 | 932 ms |

- **Neither change helps much on its own; together they do.** Smaller chunks fix the truncation, and keyword search finds exact terms the embedder misses ("OATH TOTP", "memberOf", "3072 characters").
- **The cross-encoder re-ranker made things worse and slower.** `ms-marco-MiniLM-L-6-v2` was trained on web-search queries, and it also truncates at 512 tokens. At 250 words it pushed the right passage out of the top 5 for 6 questions, and it added about 1 s per question. I left it out. A re-ranker trained on technical documentation might do better, but that wasn't tested here.
- Hit@1 is lower with small chunks, but it doesn't matter much here: all 5 chunks go to the model, so what counts is whether the right one is among them.

### What's still wrong

- **15% of answers make a claim their citation doesn't fully support.** I read each one. None invents a fact; they are small inferences beyond the quoted text, for example "a middle initial will fail an exact match" when the passage only says the names must match exactly. A stricter prompt is the next thing to try, measured against this same eval.
- **1 answer is partial** (q09): it explains report-only mode but leaves out that it doesn't apply to User Actions policies.
- **Answers sometimes repeat a fact twice**, once in the model's own words and once close to the quoted wording. Harmless but wordy.

### How much to trust these numbers

- **41 answerable questions is a small set.** One question is 2.4 percentage points, so differences of one or two questions are noise. The baseline-vs-improved gap (85% → 98% correct, 80% → 95% retrieved) is 5–6 questions.
- **Correctness and groundedness are graded by an LLM** (Claude Sonnet 5.5, a different model from the one answering, so it isn't grading its own work). Re-grading the same baseline answers moved "correct" from 83% to 85%, so the judge's own noise is about one question. Retrieval and "I don't know" metrics are exact string checks, with no judge.
- **I wrote the questions** from the documents, so they can share wording with the text. To limit that, they are phrased the way a helpdesk ticket would put them ("A user restored Authenticator on a new phone and it says 'Sign in to add your account'. Is something wrong?"), not copied from the docs.

## Cost and speed

Every question is logged to `logs/usage.jsonl` with input and output tokens, cost, and retrieval / LLM / total time. The question text is not logged, only its length, since questions can contain personal data.

| Per question (improved setup) | |
|---|---|
| Input tokens (system prompt + 5 chunks + question) | 4,441 avg |
| Output tokens (including the model's reasoning) | 510 avg |
| Cost | $0.00070 (input $0.10 / output $0.50 per million tokens) |
| **Cost per 1,000 questions** | **$0.70** |
| Retrieval time | 40 ms avg (embedding + Chroma + BM25, on CPU) |
| LLM time | 2.8 s avg |

Almost all the latency is the LLM call. Running the full eval once costs about $0.03 for the answers plus $0.16 for the Sonnet judge.

## How it works

1. **Corpus** ([scripts/fetch_corpus.py](scripts/fetch_corpus.py)): 198 Markdown pages from [MicrosoftDocs/entra-docs](https://github.com/MicrosoftDocs/entra-docs) (MIT licence), pinned to commit `59b123d` so the eval keeps pointing at the same text. Each is saved in `data/` and listed in `data/manifest.jsonl` with its learn.microsoft.com URL.
2. **Ingestion** ([src/ingest.py](src/ingest.py)): extracts text from Markdown, PDF (pypdf), HTML or plain text, and removes Microsoft Learn's markup (includes, image tags, zone pivots). It then packs whole paragraphs into 250-word chunks with 50 words of overlap. Each chunk keeps its document title, URL, section heading, and page number (for PDFs; a chunk never spans a page break, so the page number is always right).
3. **Embeddings** ([src/store.py](src/store.py)): `BAAI/bge-small-en-v1.5` (free, local, 384 dimensions), embedding "title > section" plus the chunk text, stored in Chroma.
4. **Retrieval**: vector search and BM25 each return 50 candidates, and reciprocal rank fusion merges them into the top 5. BM25 uses Lucene's IDF formula: the one in `rank_bm25` gives a word zero or negative weight once it appears in half the chunks, so on a small index (a couple of uploaded files) keyword search returned nothing.
5. **Answer** ([src/llm.py](src/llm.py)): the chunks go to Claude Haiku 5.5 as `search_result` content blocks with citations enabled. The system prompt says: answer only from these sources, cite every claim, and say "I don't know" if the answer isn't there. Each chunk is split into one text block per paragraph, so citations point at the exact paragraph, not the whole chunk.
6. **API** ([src/main.py](src/main.py)): FastAPI, same structure as Project 1 (data converter): `X-API-Key` auth that refuses to start without a key, rate limiting, upload size limits, and JSON logs.

## API

```bash
curl -X POST localhost:8000/ask -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"question": "How long can a Temporary Access Pass be valid?"}'
```

```json
{
  "answer": "A Temporary Access Pass can be configured to stay valid for up to 30 days. The policy's maximum lifetime accepts values from 10 to 43,200 minutes (30 days)[1], and the default maximum is 8 hours[1]. ... Users must reauthenticate with different authentication methods after the TAP is expired or deleted.[2]",
  "answered": true,
  "sources": [
    {
      "n": 1,
      "title": "Configure a Temporary Access Pass in Microsoft Entra ID to register passwordless authentication methods",
      "url": "https://learn.microsoft.com/en-us/entra/identity/authentication/howto-authentication-temporary-access-pass",
      "section": "Enable the Temporary Access Pass policy",
      "page": null,
      "chunk_id": "identity/authentication/howto-authentication-temporary-access-pass#2",
      "quotes": ["| Setting | Default values | Allowed values | ... | Maximum lifetime | 8 hours | 10 – 43,200 Minutes (30 days) | ..."]
    }
  ]
}
```

| Endpoint | |
|---|---|
| `GET /health` | No key needed. |
| `POST /ask` | `{"question": "..."}` → `{answer, answered, sources[]}`. 502 if the LLM call fails. |
| `POST /documents` | Multipart upload (`.pdf`, `.md`, `.txt`, `.html`), optional `url` and `title` form fields. Returns the number of chunks indexed. Re-uploading a file with the same name replaces it. |
| `GET /docs` | Interactive API docs. |

## Run it

Needs Python 3.12 and an [Anthropic API key](https://platform.claude.com/) for the answer step. Building the index and the retrieval eval need no key.

```bash
uv venv --python 3.12 && uv pip install -r requirements-dev.txt   # or: python -m venv .venv && pip install ...
cp .env.example .env            # set API_KEY and ANTHROPIC_API_KEY

python -m src.cli build         # embed data/ into index/ (about 2 minutes on CPU)
python -m src.cli ask "Can admins use security questions to reset their password?"

uvicorn src.main:create_app --factory --port 8000    # the API
python app.py                                        # the Gradio demo, http://127.0.0.1:7860
```

With Docker (the image includes the models and the built index):

```bash
docker build -t document-qa .
docker run -p 8000:8000 -e API_KEY=... -e ANTHROPIC_API_KEY=... document-qa
```

### Evaluate

```bash
python -m evals.run_eval check        # every expected passage exists in the corpus
python -m evals.run_eval retrieval    # the 8 retrieval setups (free; needs both indexes:
                                      #   python -m src.cli build --chunk-words 600 --overlap-words 100)
python -m evals.run_eval answers --label "improved 250w hybrid" --chunk-words 250 --overlap-words 50 --retrieval hybrid
```

The test questions are in [evals/questions.jsonl](evals/questions.jsonl). Each has a reference answer and an **evidence phrase** copied from the document that answers it. A retrieved chunk counts as "the right passage" if it contains that phrase. That works the same for any chunk size, unlike matching chunk ids. Full per-question reports, including every wrong or partial answer and the judge's reasoning, are in [reports/](reports/).

### Tests

```bash
pytest        # 42 tests, 92% coverage; no network or model downloads (hashing embedder, scripted LLM)
ruff check . && ruff format --check .
```

CI runs lint, tests, the evidence check, a Docker build, and a smoke test of the built image.

## Deploy

- **Demo on Hugging Face Spaces (free):** [docs/huggingface-spaces.md](docs/huggingface-spaces.md). `scripts/make_space.sh` assembles the Space.
- **API on Azure Container Apps:** [docs/azure-deployment.md](docs/azure-deployment.md), including how the vector store would move to Azure AI Search.

## Limitations

- **English only.** The embedding model and the corpus are English.
- **Uploaded documents live in the container's filesystem.** They are lost when a container restarts, unless `index/` is on a persistent volume.
- **The corpus is a snapshot** from one commit. Microsoft updates these pages often, so re-run `fetch_corpus.py` (with a new commit) and the eval to refresh it.
- **Single-turn.** There's no chat history; each question stands alone.
- Not affiliated with Microsoft. Answers can be wrong; check the cited page.

## Project layout

```
src/            config, ingest (extract + chunk), store (Chroma, BM25, hybrid), llm (Claude + citations),
                rag (pipeline + usage log), main (FastAPI), cli
app.py          Gradio demo
data/           198 Entra ID docs + manifest.jsonl (source URLs)
evals/          questions.jsonl (47 questions) and run_eval.py
reports/        retrieval and answer eval results
scripts/        fetch_corpus.py, make_space.sh
tests/          unit and API tests
docs/           deployment guides
```
