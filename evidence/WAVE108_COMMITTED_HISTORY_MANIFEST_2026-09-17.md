# Wave 108 — multi-epoch committed-history manifest

Status: **experimental PASS for the tested protocol gate; no merge / no CANON promotion**

## Why this wave changed direction

Independent verifier PR #32 tested exact Wave 107 builder head `22289521483fe8e171f6c9016f0bd0b10e54a235` and found a bounded multi-epoch history-completeness failure. After two accepted epochs, deleting only the newest epoch-2 authority-link body while retaining its signed checkpoint, signer-use row, the older valid authority link, lineage/certificate/remote/binding state and runtime made the Wave 107 history guard return `VALID`. The verifier did **not** obtain stale authority: the lower external/certificate layers still held both tested full-authority paths non-authoritative.

Exact verifier provenance:
- verifier PR: `#32`
- verifier head: `3573711a726b527d43dd056ca2bfdbdd5be81c0a`
- verifier evidence blob: `154cdc9cbc197d75a814a2b29e945d02e9d9f454`
- verifier reproducer blob: `010c59d1de7f8ce3dac8029bf620b789b134ecf2`
- verifier CI run: `35193912823`

## What Wave 108 adds

Wave 108 adds two append-only, content-addressed marker chains inside the modeled authority state:

1. `W108_COMMITTED_AUTHORITY_LEDGER` — one predecessor-linked record per accepted authority epoch, naming the exact authority link, checkpoint and signer-use identities.
2. `W108_COMMITTED_HIGH_WATER_LEDGER` — a paired predecessor-linked high-water record naming the exact commit-ledger record and authority identity.

An authority read now requires both ledgers to be linear, contiguous and mutually consistent, and every manifested committed authority link must still fully resolve. Deleting a committed link can no longer hide behind an older surviving link.

Prepared-but-uncommitted next-epoch evidence remains distinguishable from committed history: it is tolerated only while the runtime still points to the last manifested committed epoch. If the lower commit advances the runtime but the Wave-108 marker is not persisted, the state fails closed with `HOLD_COMMITTED_HISTORY_INCOMPLETE` instead of guessing whether the new epoch committed.

Wave-107 histories that predate these marker chains are deliberately **not** silently retrofitted; an explicit separately verified migration path is required.

## Exact tested source

- tested source commit: `7b9ec8548bde69df1d8971567aaf04abd0fa2e5c`
- Wave 108 tool blob: `629318c9645649a29d7a4d4c97f106a0ba958f6d`
- Wave 108 self-test blob: `aeac803084fc05e82c626bb830cee48146c710e2`
- Wave 108 workflow blob: `506b816be3877bfdd45290b8705893a597139837`
- successful CI run: `35196565048`
- successful CI job: `105121078833`
- artifact: `wave108-exact-source-reports`
- artifact digest: `sha256:76ea4bec6a68e47df60ba918bc67891253e9c16056455d489626b1cd895bbd88`

Successful exact-source results:
- unchanged Wave 107 regression: **22/22**
- Wave 108 normal Python: **27/27**
- Wave 108 `python -O`: **27/27**

The exact PR #32 mutation is reproduced first against Wave 107 as `VALID`; the same newest committed-link loss under Wave 108 is `INCOMPLETE_OR_CORRUPT`, and the authority result is `HOLD_COMMITTED_HISTORY_INCOMPLETE`.

Other tested negative cases include newest committed `L` loss, newest `L+C`, `L+U`, `L+C+U` loss, middle committed-link loss, missing newest commit marker, missing newest high-water marker, marker hash tamper, and the lower-commit / missing-Wave-108-marker crash boundary. Positive cases include genesis, normal epochs 1 and 2, prepared-but-uncommitted next-epoch evidence, and forward history through retained depth 8.

A depth-16 run is included only as **synthetic retained-depth correctness scaling**. It checks newest/middle committed-link loss and makes no performance, energy, retained-compute, incremental-compute or dormant-compute claim.

## Preserved failures and counterexamples

The first Wave 108 CI attempt (`35196179603`) failed before the protocol assertions because the self-test tried to `deepcopy()` a credential-bound certificate-witness endpoint. Wave 104 intentionally forbids that clone operation. The follow-up diagnostic run (`35196248449`) preserved the same traceback in artifact digest `sha256:3f177c54e2bb06b6e41d8cdd10459bae0df8adbd667d694d20692b56958559a8`. The self-test was then repaired to use the already-defined registered endpoint disk-snapshot / restore contract instead of cloning credentials. Those failed runs remain in repository/CI history; they were not rewritten away.

Counterexamples still preserved after the successful run:
- coordinated rollback/truncation of the whole modeled authority world, both Wave-108 marker chains and supporting external state to an older genuine prefix can still look internally valid;
- the lower-commit -> Wave-108-marker persistence window is fail-closed but not atomically recoverable;
- both new marker chains remain in the same modeled Python failure domain and therefore do not prove physically monotonic storage;
- existing symmetric modeled credentials and fixed certificate-witness-root limits remain;
- all current process/device/provider independence claims remain explicitly unproven.

## Next gate

**Wave 109: durable process separation with the Wave-108 manifest contract.** Put the repaired authority + committed-history + bootstrap/certificate contract into separate OS processes and durable stores, then attack kill/restart at the commit->marker boundary, stale/cloned disk restoration, newest/middle marker truncation, one process offline plus one stale process, partitions/reconnects, simultaneous old/new process views, and whole-process rollback. Keep a distinct later gate for explicit migration of pre-Wave-108 histories; do not silently synthesize marker history.

A clean Wave 109 result would establish process-level persistence evidence only. It would not by itself prove physical/device/provider independence or that retained/incremental/dormant compute is superior.
