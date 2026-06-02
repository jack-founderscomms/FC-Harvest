"""
Entry points:
  python run.py serve    — start the web dashboard (default port 8000)
  python run.py harvest  — run a single harvest now and exit
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
            print(f"    - {e}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "harvest":
        harvest()
    else:
        serve()
