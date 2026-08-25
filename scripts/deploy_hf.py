"""Push MANTIS to a Hugging Face Docker Space — the third submission artifact.

    python scripts/deploy_hf.py --check                      # preflight only
    python scripts/deploy_hf.py --space <user>/mantis
    python scripts/deploy_hf.py --space <user>/mantis --token hf_xxx

Why Spaces, and why one container
---------------------------------
The deadline argument is availability, not elegance. A free Render or Railway
dyno **sleeps after ~15 minutes idle and takes ~30 s to wake**, which is exactly
the shape of a demo that looks broken at the moment a judge clicks it. A Docker
Space stays warm on the free tier and serves the console and the API from one
origin, so there is no CORS preflight, no second service to keep alive, and one
URL to hand over. See ``mantis/api/site.py`` for the composition.

What gets uploaded
------------------
Only what ``Dockerfile`` actually copies: the package, the web sources, the
committed LLM cache, the small JSON artefacts, ``RESULTS.md`` and ``docs/``.
Explicitly **not** the parquets (hundreds of megabytes), the pickled experiment,
or the Kaggle reference CSVs. The upload is a few megabytes; the Space builds the
front end itself from ``web/src`` in the Dockerfile's node stage.

``README.md`` on the Space is ``deploy/hf/README.md``, not the repo's own: Spaces
reads YAML frontmatter out of the README to learn the SDK and the port, and
putting that frontmatter in the repo's README would leave a stray metadata table
at the top of the GitHub page.

Credentials
-----------
A write token from https://huggingface.co/settings/tokens, passed as ``--token``,
in ``$HF_TOKEN``, or already stored by ``hf auth login``. It is never written into
the repo. HARD RULE 4 is about a clean clone needing no credentials, and it
applies to this script as much as to anything else: deployment is the one place
a token is used, and it is supplied at the command line.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Final

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # so the script runs without an editable install
    sys.path.insert(0, str(REPO_ROOT))

#: Exactly the paths ``Dockerfile`` needs, as ``upload_folder`` glob patterns.
#: Kept in one list so drift between the two is a visible edit rather than a
#: build failure ten minutes into a push.
ALLOW: Final[list[str]] = [
    "Dockerfile",
    ".dockerignore",
    "pyproject.toml",
    "RESULTS.md",
    "mantis/**",
    "web/src/**",
    "web/public/**",
    "web/index.html",
    "web/package.json",
    "web/package-lock.json",
    "web/tsconfig.json",
    "web/vite.config.ts",
    "data/cache/**",
    "data/generated/*.json",
    "data/reference/l3_ood_payloads.json",
    "docs/**",
]

#: Belt and braces over ALLOW. A parquet reaching a Space is a slow push and a
#: fat image; a CSV reaching one is half a gigabyte of somebody else's data.
IGNORE: Final[list[str]] = [
    "**/__pycache__/**",
    "**/*.pyc",
    "**/*.parquet",
    "**/*.csv",
    "**/*.zip",
    "**/*.pkl",
    "web/node_modules/**",
    "web/dist/**",
]

#: Files whose absence would produce a Space that builds and then serves an empty
#: console. Checked before the upload rather than discovered after it.
REQUIRED: Final[list[str]] = [
    "Dockerfile",
    "RESULTS.md",
    "deploy/hf/README.md",
    "web/index.html",
    "web/package-lock.json",
    "web/public/data/results.json",
    "data/generated/console_feed.json",
    "data/generated/arena.json",
]


def preflight() -> list[str]:
    """Return the problems that would make the deployed Space wrong. Empty is good."""
    problems: list[str] = []
    for rel in REQUIRED:
        if not (REPO_ROOT / rel).is_file():
            problems.append(f"missing: {rel}")

    scorecard = REPO_ROOT / "data" / "generated" / "fidelity.json"
    if not scorecard.is_file():
        problems.append(
            "missing: data/generated/fidelity.json - the Fidelity screen will render "
            "its 'not measured' panel. Run: make fidelity"
        )

    frozen = REPO_ROOT / "web" / "public" / "data" / "fidelity.json"
    if frozen.is_file() and scorecard.is_file():
        payload = json.loads(frozen.read_text(encoding="utf-8"))
        if not payload.get("available"):
            problems.append(
                "stale: web/public/data/fidelity.json says available:false but the "
                "scorecard exists. Run: make static"
            )
    return problems


def resolve_token(explicit: str | None) -> str | None:
    """Token from the flag, then the environment, then whatever ``hf auth`` stored."""
    if explicit:
        return explicit
    env = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if env:
        return env
    try:
        from huggingface_hub import get_token

        return get_token()
    except Exception:  # an absent or older huggingface_hub is not an error here
        return None


def _selected_files() -> list[str]:
    """The repo-relative paths ``upload_folder`` would send, in order."""
    from huggingface_hub.utils import filter_repo_objects

    every = [
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in REPO_ROOT.rglob("*")
        if p.is_file()
    ]
    return sorted(filter_repo_objects(every, allow_patterns=ALLOW, ignore_patterns=IGNORE))


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy MANTIS to a Hugging Face Space.")
    parser.add_argument(
        "--space",
        default=os.environ.get("MANTIS_SPACE", ""),
        help="target Space as <user-or-org>/<name>. Also read from $MANTIS_SPACE.",
    )
    parser.add_argument("--token", default=None, help="HF write token (or set $HF_TOKEN)")
    parser.add_argument("--private", action="store_true", help="create the Space private")
    parser.add_argument(
        "--check",
        action="store_true",
        help="run the preflight and print what would be uploaded, then stop",
    )
    args = parser.parse_args()

    print("MANTIS -> Hugging Face Space")
    print()

    problems = preflight()
    for problem in problems:
        print(f"  ! {problem}")
    if not problems:
        print("  preflight  all required artefacts present")
    print()

    if args.check:
        selected = _selected_files()
        total = sum((REPO_ROOT / rel).stat().st_size for rel in selected)
        print(f"  would upload {len(selected)} files, {total / 1e6:.1f} MB")
        head = [rel for rel in selected if not rel.startswith("data/cache/llm/")]
        for rel in head[:20]:
            print(f"    {rel}")
        print(f"    ... plus {len(selected) - len(head)} LLM cache entries")
        return 0

    if not args.space or "/" not in args.space:
        print("  --space <user>/<name> is required (or set $MANTIS_SPACE).")
        return 2

    token = resolve_token(args.token)
    if not token:
        print("  No Hugging Face token. Pass --token, set $HF_TOKEN, or run 'hf auth login'.")
        print("  Create one at https://huggingface.co/settings/tokens with write scope.")
        return 2

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    print(f"  authenticated as {api.whoami().get('name')}")

    api.create_repo(
        repo_id=args.space,
        repo_type="space",
        space_sdk="docker",
        private=args.private,
        exist_ok=True,
    )
    print(f"  space ready  {args.space}")

    # The Space card goes first: if the folder upload triggers a build, the build
    # already knows it is a Docker Space listening on 7860.
    api.upload_file(
        path_or_fileobj=str(REPO_ROOT / "deploy" / "hf" / "README.md"),
        path_in_repo="README.md",
        repo_id=args.space,
        repo_type="space",
        commit_message="Space card: docker sdk, port 7860",
    )
    print("  uploaded     README.md (Space card)")

    api.upload_folder(
        folder_path=str(REPO_ROOT),
        repo_id=args.space,
        repo_type="space",
        allow_patterns=ALLOW,
        ignore_patterns=IGNORE,
        commit_message="MANTIS: console and API in one container",
    )
    print("  uploaded     the build context")

    subdomain = args.space.replace("/", "-").replace("_", "-").lower()
    print()
    print(f"  Space    https://huggingface.co/spaces/{args.space}")
    print(f"  App URL  https://{subdomain}.hf.space")
    print()
    print("  The first build takes ~3-5 minutes (npm ci, then pip). Watch the")
    print("  Logs tab. Then open the app URL ON A PHONE and press")
    print("  'Start authorisation stream' before you believe it works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
