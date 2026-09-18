#!/usr/bin/env python3
"""Wave 114 CI harness compatibility shim.

The first Wave-114 CI attempt failed before exercising the implementation because the self-test
referenced ``w.PROVENANCE_STORE`` while the additive Wave-114 module intentionally kept that
constant on its Wave-113 predecessor. This shim exposes only that predecessor constant to the
self-test process, without changing Wave-114 decision/recovery logic or rewriting the failed run.
"""
import AXM_FLOWING_COMPUTE_EXACT_TRANSITION_DECISION as w
import AXM_FLOWING_COMPUTE_RECOVERY_ATOMICITY as w113

w.PROVENANCE_STORE = w113.PROVENANCE_STORE

import AXM_FLOWING_COMPUTE_EXACT_TRANSITION_DECISION_SELFTEST as selftest

if __name__ == "__main__":
    raise SystemExit(selftest.main())
