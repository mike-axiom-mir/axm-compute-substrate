# Flowing Compute Wave 124 — exclusive process-witness lifetime lease

Status: **PASS, experimental lane only, unmerged/non-CANON**.

## Why this wave exists

Independent verifier PR #48 reproduced a real Wave 123 race: two genuine witness processes could overlap on the same witness directory and credential. The replacement process could unlink/rebind the configured Unix socket while an already-established connection to the old process remained valid. Both processes could load the same ledger prefix and independently accept contradictory terminal outcomes at the same next sequence. Later full-ledger verification failed closed, but two authenticated contradictory acknowledgements had already existed.

Verifier identity preserved by Wave 124:

- verifier PR: `#48`
- verifier head: `b58c6ab768bb6eaf2400a542db8e960041fc2b25`
- verifier artifact SHA-256: `3f1f64de3a8836588285e40f411f106abf18cd4616083732d051072e096afdaf`

## Repair

Wave 124 adds a **store-scoped lifetime lease** before any witness process may inspect/unlink the socket, load the credential/ledger, or answer requests. The lease is a non-blocking Linux `flock` held for the complete server lifetime.

Important ordering invariant:

1. acquire exclusive witness-store lease;
2. validate exact witness identity and append-only ledger;
3. only then remove a stale Unix-socket path and bind;
4. keep the lease until the listener is closed and owned socket cleanup completes.

A rejected overlapping process therefore cannot unlink the active socket. `SIGKILL` releases the kernel lock automatically; a stale zero-byte `serve.lock` file is operational metadata only and is never interpreted as evidence or authority.

## Exact tested source

Commit: `959e4c46e7c2ecf8e2043ebaa177b696d7d35f31`

Source blobs:

- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_EXCLUSIVE.py` — `d8ececaab8aedd3ca9543b36c5e90d9130d19905`
- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_EXCLUSIVE_SELFTEST.py` — `c2a916feebb3026a434cd0f25eb777efb0729bd4`
- `.github/workflows/wave124-exclusive-process-witness.yml` — `8aef21e706aeddc7cefb8b6784eb65ecaec87664`
- unchanged Wave 123 tool — `2e87f9416d8ec0d9d04b46e842ac2d7a1a9e0f08`
- unchanged Wave 123 self-test — `cb7828109185284a9d543a697a85129a3273d7a9`

GitHub Actions:

- run: `35288384036`
- job: `105425665455`
- artifact: `10525082606` (`wave124-report`)
- artifact SHA-256: `e4b5fb8be91366487d2b3334a27f5dea4dc50e8ecea1f964170a178703a12c4d`

Results:

- unchanged Wave 123 regression: **19/19 PASS**
- unchanged Wave 123 regression under `python -O`: **19/19 PASS**
- Wave 124: **13/13 PASS**
- Wave 124 under `python -O`: **13/13 PASS**

## Positive and negative controls

Wave 124 directly confirmed the Wave 123 prerequisite defect by starting two unchanged Wave 123 servers on the same store/socket while an established connection to the old instance remained live. Under Wave 124 the same replacement attempt exits with `RuntimeError:witness-store-already-served` before touching the socket; the socket inode remains unchanged, the old established connection still reaches the original PID, the normal socket path still reaches that same PID, and the witness ledger remains byte-identical.

The lease is store-scoped rather than socket-scoped: attempting to serve the same witness directory on a different socket also fails. Two different witness stores may serve concurrently. Normal COMMIT, exact idempotent retry, terminal-conflict rejection, and corrupt-ledger startup failure remain intact.

An actual `SIGKILL` of the active Wave 124 witness leaves the durable ledger/local receipt intact, releases the kernel lease, and allows an exact successor process to acquire the same store, remove the stale socket pathname, preserve the credential fingerprint, and return the prior COMMIT as authoritative. A corrupt startup also releases the lease so exact repair and restart are possible.

## Truth boundary / surviving counterexamples

This closes the tested **overlapping cooperating-server race on one Linux host**. It does **not** prove:

- power-loss, kernel, controller, filesystem, or device finality;
- safety on filesystems where advisory locking semantics differ;
- safety against a writer that bypasses the Wave 124 server and edits ledger files directly;
- safety against witness-directory/inode substitution while a server is live;
- network or provider independence;
- protection when both witness state and the independently retained client pin are rolled back/replaced together.

No real AXM/monolith performance workload and no synthetic scaling workload were run for this correctness gate. No speed, energy, retained-compute, incremental-compute, or dormant-compute claim is made.

## Next gate

Before process-boundary referee rotation, attack **live witness-directory/inode substitution and cloned-store fork scenarios**: rename/swap the active witness directory, clone the exact credential + ledger prefix, serve the clone on a replacement path/socket, and test whether old established connections and new clients can observe diverging but individually authenticated histories. If that survives, bind the live process to an opened store directory identity (or equivalent stronger store handle) and then continue to old-root-authorized witness/referee rotation across the process boundary.

No merge, auto-merge, or CANON promotion was performed.
