"""Download the document corpus: public Microsoft Entra ID admin docs.

Source: https://github.com/MicrosoftDocs/entra-docs (MIT licence), pinned to one commit so
the eval set keeps pointing at the same text. Each file is saved under data/docs/ and listed
in data/manifest.jsonl with the learn.microsoft.com URL it is published at, which is what
the citations link to.

    python scripts/fetch_corpus.py            # download (skips files already present)
    python scripts/fetch_corpus.py --list     # only print the selection
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = "MicrosoftDocs/entra-docs"
COMMIT = "59b123da699e70670d284da5ee179ba5684b32aa"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Helpdesk topics: sign-in methods, MFA, password reset, users and groups, Conditional Access.
FOLDERS = {
    "docs/identity/authentication/": (
        r"sspr|mfa|password|passkey|authenticator|temporary-access|account-recovery"
        r"|authentication-methods|registration|security-key|phone|sms|oath|number-match"
        r"|overview-authentication|system-preferred|mandatory|security-questions|email-signin",
        r"nps-extension|adfs|server-migration|mfa-server|on-premises|telephony|data-residency"
        r"|regional|kerberos|cost-savings|videos|rdp|macos|federation|external-method"
        r"|reporting-datacollection|authprovider",
    ),
    "docs/identity/users/": (
        r".",
        r"powershell|cmdlets|linkedin|licensing-service-plan-reference|graph-examples",
    ),
    "docs/identity/conditional-access/": (
        r".",
        r"agent|autonomous|security-copilot|deployment-guide",
    ),
}


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "rag-corpus-fetch"})  # noqa: S310 (fixed https URLs)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                return response.read()
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def select_paths() -> list[str]:
    tree_url = f"https://api.github.com/repos/{REPO}/git/trees/{COMMIT}?recursive=1"
    tree = json.loads(_get(tree_url))
    if tree.get("truncated"):
        sys.exit("GitHub returned a truncated tree; cannot select files reliably.")
    paths = []
    for item in tree["tree"]:
        path = item["path"]
        if not path.endswith(".md") or "/includes/" in path:
            continue
        for folder, (include, exclude) in FOLDERS.items():
            name = path.removeprefix(folder)
            if path.startswith(folder) and "/" not in name:
                if re.search(include, name) and not re.search(exclude, name):
                    paths.append(path)
    return sorted(paths)


def public_url(path: str) -> str:
    # docs/identity/users/foo.md -> https://learn.microsoft.com/en-us/entra/identity/users/foo
    return "https://learn.microsoft.com/en-us/entra/" + path.removeprefix("docs/")[: -len(".md")]


def title_of(text: str) -> str:
    match = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip().strip("'\"") if match else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="print the selection and exit")
    args = parser.parse_args()

    paths = select_paths()
    print(f"{len(paths)} documents selected from {REPO}@{COMMIT[:7]}")
    if args.list:
        print("\n".join(paths))
        return

    def fetch(path: str) -> dict:
        target = DATA / path.removeprefix("docs/")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_get(f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{path}"))
        text = target.read_text(encoding="utf-8")
        return {
            "doc_id": path.removeprefix("docs/")[: -len(".md")],
            "file": str(target.relative_to(DATA)),
            "url": public_url(path),
            "title": title_of(text),
            "repo_path": path,
        }

    with ThreadPoolExecutor(max_workers=8) as pool:
        entries = list(pool.map(fetch, paths))

    with open(DATA / "manifest.jsonl", "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"wrote {len(entries)} files and data/manifest.jsonl")


if __name__ == "__main__":
    main()
