# Flowing Compute — Wave 117 outcome-authority root anchor

Date: 2026-09-17
Lane: `chatgpt/lane-001-platform-extract` / PR #2 (experimental, unmerged)

## Result

Wave 117 is green at exact tested source commit `1c033d96e792c9f8532bf2355c9f1ec958da969a`.

Independent verifier PR #41 had shown that Wave 116's HMAC outcome authority could be replaced together with the mutable binding and resealed rejection/outcome history. Wave 117 roots the exact outcome-authority identity into the already signed Wave-105 checkpoint/root-binding path through a content-addressed outcome root plus app envelope.

The Wave-117 self-test explicitly reproduces the PR #41 substitution against unchanged Wave 116, then shows the same substitution fails closed under Wave 117. Root-body tamper, root-store replacement, envelope tamper, normal reject→genuine commit, and two accepted app-state epochs preserving one root are covered. The exact-source Wave-117 report is 22/22 with 0 failures. The workflow also reruns the unchanged Wave-116 regression in normal and `python -O` modes, and runs Wave 117 in both modes.

## Exact identities

- tested source commit: `1c033d96e792c9f8532bf2355c9f1ec958da969a`
- tool blob: `c2d3b7f9176f24dc9fd5599527bb3619f89f01e7`
- self-test blob: `859365b19e5cd9537b49144f9e43303affd281eb`
- workflow blob: `e5e557fc0fb232c092bd6760ace9a717633ffa95`
- GitHub Actions run: `35249201898`
- job: `105297045575`
- artifact: `10509393416` (`wave117-report`)
- artifact SHA-256: `cc4cdf2fea411835c63570be7b0e3408ed45a8377f1611ac334482705a8c16d1`

## Truth boundary / preserved counterexamples

This result proves a same-process checkpoint-anchored identity contract only. It does **not** prove OS-process isolation, separate durable-device finality, physical monotonicity, provider independence, network consensus, energy improvement, or a retained/incremental/dormant-compute performance win.

The initial outcome-root choice remains a bootstrap/configuration boundary before the first accepted checkpoint. Outcome-authority rotation is intentionally unsupported in Wave 117. Whole-modeled-domain rollback remains a live counterexample because every modeled fact, including the anchor, can still be rolled back together.

No merge, auto-merge, or CANON promotion is authorized or performed by this evidence record.

## Next gate

Add old-root-authorized outcome-authority rotation with append-only lineage. Positive and negative tests must cover exact predecessor authorization, old/new-root crossover, substituted successor credentials, root-body/tail tamper, replay, crash after the new root is checkpointed but before live activation, and retained rejection outcomes on both sides of a rotation. Only after the lineage is explicit should the outcome witness move to a separate OS process/store.