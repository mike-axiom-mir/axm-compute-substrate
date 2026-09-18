#!/usr/bin/env python3
"""Wave 125 self-test harness repair.

The first Wave 125 CI run exposed a verifier-only race: launch_expect_fail killed a
correctly failing child immediately after its error file appeared, before the child
had time to exit with code 2. That produced returncode -9 and one false-negative
control even though the expected `witness-credential-already-live-on-host` error
was already present and all later safety/recovery controls passed.

This wrapper changes only that harness wait. It imports and runs the unchanged
Wave 125 adversarial suite after replacing launch_expect_fail with the same
wait-for-clean-exit behavior used by the proven Wave 124 harness.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_HOSTBOUND_SELFTEST as base


def launch_expect_fail(tool: Path, wd: Path, sock: Path, ready: Path, error: Path,
                       timeout: float = 5.0) -> dict:
    for p in (ready, error):
        if p.exists():
            p.unlink()
    proc = subprocess.Popen(
        [sys.executable, str(tool), "serve", str(wd), str(sock),
         "--ready-file", str(ready), "--error-file", str(error)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    end = time.time() + timeout
    while time.time() < end and proc.poll() is None and not error.exists() and not ready.exists():
        time.sleep(0.02)

    if proc.poll() is None and (error.exists() or ready.exists()):
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    elif proc.poll() is None:
        proc.kill()
        proc.wait(timeout=2)

    out, err = proc.communicate() if proc.stdout is not None else ("", "")
    return {
        "returncode": proc.returncode,
        "ready": ready.exists(),
        "error": error.read_text().strip() if error.exists() else "",
        "stdout": out,
        "stderr": err,
    }


base.launch_expect_fail = launch_expect_fail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report")
    ns = ap.parse_args()
    report = base.run()
    report["harness_repair"] = {
        "first_failed_run": 35292893987,
        "first_failed_job": 105439352425,
        "first_failed_artifact": 10526407948,
        "first_failed_artifact_sha256": "080eadc9394f6bd92983f5b353df33911ff62feba2e2b85c68c051d80c55791c",
        "repair": "wait up to one second for expected failing child to exit after error marker before SIGKILL fallback",
        "implementation_changed": False,
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if ns.report:
        Path(ns.report).write_text(text + "\n")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
