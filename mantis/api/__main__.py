"""Run the MANTIS API.

    python -m mantis.api                    # 127.0.0.1:8000
    python -m mantis.api --host 0.0.0.0 --port 8080 --reload

Binds to loopback by default. A deployment passes ``--host 0.0.0.0`` explicitly,
which is the right way round: a demo server that listens on every interface
because that was the default is a demo server exposed on conference wifi.
"""

from __future__ import annotations

import argparse
import os

from mantis.api.store import STORE


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the MANTIS console API.")
    parser.add_argument("--host", default="127.0.0.1")
    # Render, Railway and Hugging Face Spaces all inject $PORT and expect the
    # process to honour it. Reading it here is what makes `python -m mantis.api`
    # a valid start command on all three without a wrapper script.
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    print("MANTIS API")
    print(f"  atlas    {STORE.headline.get('atlas_cards')} cards, "
          f"{STORE.headline.get('atlas_implemented')} implemented")
    print(f"  feed     {len(STORE.events)} pre-scored events")
    print(f"  results  {'loaded' if STORE.results else 'MISSING (run make firewall)'}")
    print(f"  arena    {'loaded' if STORE.arena else 'MISSING (run make loop)'}")
    print(f"  -> http://{args.host}:{args.port}/docs")
    print()

    import uvicorn

    uvicorn.run(
        "mantis.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
