"""Bounded, lightweight replacement for the existing scheduled-job entrypoint."""

import sys

from poligrapher_app.cost_worker import run_bounded


if __name__ == "__main__":
    # Budget checks never consume the expensive worker allocation. Preserve the
    # existing schedule publisher, with a bounded runtime; it only enqueues work.
    result = run_bounded([sys.executable, "-m", "poligrapher_app.run_due_schedules"], 10)
    if result:
        print("Schedule publishing failed; already queued work may still dispatch", flush=True)
    sys.exit(run_bounded([sys.executable, "-m", "poligrapher_app.cost_guard"], 40))
