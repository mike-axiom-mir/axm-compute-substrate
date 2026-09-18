#!/usr/bin/env python3
"""Wave 128 protocol regression self-test through the key-custody wrapper."""
from __future__ import annotations

import sys

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_CUSTODY as custody

# Reuse the full Wave-127 protocol/adversarial suite while forcing parent and
# subprocess servers through the Wave-128 candidate. This preserves the old
# socket-substitution, replay, tamper, restart, and request-binding controls.
sys.modules["AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR"] = custody

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR_SELFTEST as original


def main() -> int:
    return original.main()


if __name__ == "__main__":
    raise SystemExit(main())
