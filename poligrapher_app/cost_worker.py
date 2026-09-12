"""Run an analysis child only with a finite allowance issued by cost_guard."""

import os
import signal
import subprocess
import sys


def run_bounded(command, seconds):
    child = subprocess.Popen(command, start_new_session=True)
    try:
        return child.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait()
        print("Runtime allowance exhausted; queued task retained for later recovery", flush=True)
        return 124
    finally:
        # Also stop analysis descendants when the main child exits unexpectedly.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main():
    seconds = int(os.environ["COST_MAX_RUNTIME_SECONDS"])
    if not 1 <= seconds <= 43200:
        raise ValueError("Missing or invalid runtime allowance")
    return run_bounded([sys.executable, "-m", "poligrapher_app.worker"], seconds)


if __name__ == "__main__":
    sys.exit(main())
