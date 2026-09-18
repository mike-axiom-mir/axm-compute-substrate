#!/usr/bin/env python3
"""Wave 127 self-test using the pinned-key OpenSSL handoff repair."""
from __future__ import annotations

import sys

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR_FIXED as fixed

# The original self-test imports the Wave 127 module by its original name and
# derives the subprocess tool from that module's __file__. Point that import at
# the exact repaired wrapper so both the parent test and child servers exercise
# the same candidate without duplicating the adversarial suite.
sys.modules["AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR"] = fixed

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR_SELFTEST as original


def main() -> int:
    return original.main()


if __name__ == "__main__":
    raise SystemExit(main())
