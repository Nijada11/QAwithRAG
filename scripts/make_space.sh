#!/usr/bin/env bash
# Assemble a Hugging Face Space (Gradio SDK) in ./space from this repo.
# See docs/huggingface-spaces.md for how to create the Space and push this folder.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf space
mkdir -p space
cp -r app.py src data space/
find space -name __pycache__ -type d -prune -exec rm -rf {} +
{ cat requirements.txt; echo "gradio==6.31.0"; } > space/requirements.txt

cat > space/README.md <<'EOF'
---
title: Entra ID Helpdesk Assistant
emoji: 🔐
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 6.31.0
app_file: app.py
pinned: false
license: mit
short_description: RAG over Microsoft Entra ID docs, with cited passages
---

Answers IT helpdesk questions from 198 pages of public Microsoft Entra ID documentation and
cites the exact passages it used. Not affiliated with Microsoft.

Needs the `ANTHROPIC_API_KEY` secret (Settings → Variables and secrets).
The index is built from `data/` on first start, which takes a few minutes on the free CPU.
EOF

echo "Space assembled in ./space ($(du -sh space | cut -f1))"
