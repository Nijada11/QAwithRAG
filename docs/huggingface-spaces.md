# Deploying the demo to Hugging Face Spaces

The Gradio demo (`app.py`) runs the whole pipeline in one process, so it fits a free
**CPU basic** Space (2 vCPU, 16 GB RAM at the time of writing; check
[Spaces hardware](https://huggingface.co/docs/hub/spaces-overview#hardware-resources)).

## Costs

- The Space itself is free on CPU basic. It sleeps after a period without visitors and
  wakes on the next visit (the first request after waking is slow).
- Every question calls the Claude API, which **your** API key pays for. At the measured
  ~$1–2 per 1,000 questions this is small, but a public demo can be used by anyone.
  Set a monthly spend limit on the key in the [Claude Console](https://platform.claude.com/)
  before you share the link, or use a separate key just for the demo.

## Steps

1. Create a Space at <https://huggingface.co/new-space>: SDK **Gradio**, hardware **CPU basic**,
   visibility as you like.
2. In the Space, open **Settings → Variables and secrets** and add a **secret**
   `ANTHROPIC_API_KEY`. Secrets are not visible to visitors or in the repo.
3. Assemble the Space folder and push it:

   ```bash
   ./scripts/make_space.sh
   cd space
   git init -b main
   git remote add origin https://huggingface.co/spaces/<your-username>/<space-name>
   git add . && git commit -m "Deploy demo"
   git push -u origin main      # log in with a Hugging Face access token (write scope)
   ```

4. Watch the **Logs** tab. The first start installs the dependencies, downloads the
   embedding model and builds the index from `data/` (a few minutes). After that the app
   shows "Running".

## Notes

- The Space's disk is not persistent on the free tier, so the index is rebuilt whenever the
  Space restarts. That is fine for 198 documents. For a bigger corpus, build the index
  locally and upload `index/` with the Space, or move to Azure AI Search.
- The demo uses the same settings as the API (`RagConfig` defaults: 250-word chunks, hybrid
  retrieval). Override them with Space **variables**, for example `LLM_MODEL`.
- Uploading documents is only possible through the API, not the public demo, so visitors
  can't change what the assistant knows.
