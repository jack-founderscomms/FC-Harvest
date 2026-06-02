"""
Entry points:
  python run.py serve    — start the live web dashboard (port 8000)
  python run.py harvest  — run a harvest and exit
  python run.py static   — generate docs/index.html for GitHub Pages
  python run.py          — same as 'serve'
"""

import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def serve():
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)


def harvest():
    from harvest.runner import run_harvest
    result = run_harvest()
    print(f"\nHarvest complete:")
    print(f"  New items : {result['new_items']}")
    print(f"  Run ID    : {result['run_id']}")
    if result["errors"]:
        print(f"  Errors ({len(result['errors'])}):")
        for e in result["errors"]:
            src = e.get("source_id", "?")
            msg = e.get("message", str(e))
            print(f"    - [{src}] {msg}")


def static():
    from generate_static import generate
    generate()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "harvest":
        harvest()
    elif cmd == "static":
        static()
    else:
        serve()
