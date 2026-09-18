#!/usr/bin/env python3
"""Wave 129 CI harness hardening only.

Run the Wave 129 adversarial self-test with a JSON-aware readiness wait. The
first exact-source CI attempt exposed a verifier race: Path.write_text() can
make the pause marker pathname visible before the JSON payload is readable, so
optimized mode occasionally observed an empty marker and failed in json.loads.

This wrapper changes no Wave 129 implementation or security assertion. It keeps
the failed CI run as evidence and makes the test handshake wait for complete
JSON when the marker suffix is .json. Child initializer probes still execute
the original adversarial self-test's --child-init path unchanged.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_LIFECYCLE_SELFTEST as _test


def _stable_wait_file(path: Path, proc: subprocess.Popen | None = None,
                      timeout: float = 12.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists():
            if path.suffix != ".json":
                return
            try:
                json.loads(path.read_text())
                return
            except (json.JSONDecodeError, OSError):
                pass
        if proc is not None and proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(
                f"process-exited-before-ready:{proc.returncode}:{out}:{err}"
            )
        time.sleep(0.02)
    raise TimeoutError(f"marker-timeout:{path}")


_test.wait_file = _stable_wait_file


if __name__ == "__main__":
    raise SystemExit(_test.main())
