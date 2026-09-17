# AXM Flowing Compute — Wave 123 evidence

Status: experimental lane only. No merge, auto-merge, or CANON promotion.

## Gate carried forward from Wave 122

Wave 122 proved bounded rollback for same-process `BaseException` termination only while its restore path could still execute. Its explicit next gate was a genuinely separate OS-process outcome/decision witness with its own durable store and credential, exercised with actual hard process kills.

Exact predecessor identity preserved here:

- Wave 122 evidence head: `41f1719b48aace2c5db5ae68cadb9ccbce14970d`
- Wave 122 tested source: `5ebe63488494c6767637b82407be8675d1fcca52`
- Wave 122 tool blob: `78df9135f97e568e64ef37b83d743d6475a8adee`
- Wave 122 self-test blob: `1818037e4e017f69c98f1e269b08fc3d2de66071`
- Wave 122 CI run: `35278477192`
- Wave 122 artifact SHA-256: `1bc3634aaff202d7da051a3fcbf3841ec6a2b8a50121fd7c3e679142ef98e8d9`

## Wave 123 change

Wave 123 introduces a reusable single-host process-witness prototype:

- the outcome witness is a genuinely separate OS process reached over a Unix-domain socket;
- it owns a distinct random credential and a content-stable credential fingerprint that the client must pin;
- witness history is append-only JSONL with an HMAC-authenticated hash chain and `fsync` on each appended record plus directory sync;
- local publication is a separate append-only/fsync'd receipt journal naming the exact witness record, transition, proposal and pinned witness identity;
- terminal `COMMIT` / stable `REJECT` are distinguished from retriable `HOLD`; `HOLD` cannot silently become terminal and an unstable terminal result is rejected;
- exact retries are idempotent rather than appending duplicate evidence;
- recovery from a witness-ahead state requires the exact authority, transition and proposal identity already retained by the witness. Semantic similarity is not accepted as recovery proof.

This is deliberately a small boundary experiment, not a replacement for the Wave 122 retained-state/rotation machinery and not CANON.

## Positive and negative process-kill tests

The exact-source adversarial suite passed **19/19** normally and **19/19** under `python -O`.

Positive/recovery cases include:

- confirmed different PIDs for test/client and witness process;
- clean COMMIT becomes `AUTHORITATIVE_PROCESS_WITNESS_COMMIT`;
- exact retry creates no duplicate witness/local ballast;
- retriable HOLD can later settle to COMMIT;
- a stable REJECT remains terminal and blocks a conflicting COMMIT;
- `SIGKILL` of the witness before durable append leaves no terminal outcome and permits a clean retry;
- `SIGKILL` of the witness after ledger `fsync` but before response leaves the witness newer, local state HOLDs, and exact recovery succeeds after restart;
- `SIGKILL` of the client after witness acknowledgement but before local append leaves `HOLD_WITNESS_AHEAD` and exact recovery succeeds;
- `SIGKILL` of the client after its local receipt `fsync` preserves the committed result;
- complete local-journal rollback while the witness remains newer is detected as `HOLD_WITNESS_AHEAD`;
- simultaneous current and stale client views produce authoritative/current versus HOLD/stale rather than both appearing current;
- witness unavailability/partition fails closed and reconnect returns to the same retained result without rewriting the ledger.

Negative/adversarial cases include:

- unstable `REJECT` and stable `HOLD` are refused without appending evidence;
- wrong-proposal recovery cannot mutate local state;
- witness ledger tail truncation prevents startup;
- witness ledger content corruption fails authentication and prevents startup;
- whole witness-store + credential substitution is rejected when the original client pin survives;
- local receipt-journal tampering fails closed;
- the witness ledger keeps the original append-only prefix across the tested failures and restarts.

## Preserved counterexample

Wave 123 deliberately keeps the stronger counterexample visible: if the experimenter rolls **both** the witness ledger and the local receipt journal back together to an older genuine prefix, the older prefix can again appear authoritative. This is expected because both stores and the surviving credential pin are still inside one host/operator failure domain.

Therefore Wave 123 establishes only the tested **separate OS-process + separate logical durable-store boundary on one Linux host**. It does not establish independent physical finality.

## Exact-source verification

Tested source commit: `b594d1bac276c11f98ce6a6f558fb929ed0c30eb`

Exact blobs:

- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS.py`: `2e87f9416d8ec0d9d04b46e842ac2d7a1a9e0f08`
- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_SELFTEST.py`: `cb7828109185284a9d543a697a85129a3273d7a9`
- `.github/workflows/wave123-separate-process-witness.yml`: `8bea5c92bdc32e0645ce2d38792431c9148c5d79`
- unchanged Wave 122 tool: `78df9135f97e568e64ef37b83d743d6475a8adee`
- unchanged Wave 122 self-test: `1818037e4e017f69c98f1e269b08fc3d2de66071`

Exact-source workflow run `35283872389`, job `105411746677`, completed successfully. Artifact `10523208489` (`wave123-report`) has GitHub digest `sha256:315c44825ff48f49c05f95e26b14d210cf70e05ba045c7cfa07854f6a11fbc90`.

Verification results:

- unchanged Wave 122 regression: **12/12 PASS**;
- unchanged Wave 122 regression under `python -O`: **12/12 PASS**;
- Wave 123: **19/19 PASS**;
- Wave 123 under `python -O`: **19/19 PASS**.

The machine-readable CI artifact is intentionally not committed into the repository; only the reusable tools and concise source-bound evidence are retained.

## Truth boundary

- `fsync` on one GitHub Actions Linux filesystem is not a claim of survival across real power loss, storage-controller failure, kernel failure, damaged media or hostile storage rollback;
- the witness credential is distinct, but the tested witness store and client are still on one host/filesystem;
- witness substitution is detected only while the independently retained client pin survives; replacing/rolling back the witness **and** that pin is still a counterexample;
- the prototype does not yet integrate Wave 118/119 outcome-authority rotation across this process boundary;
- no network-separated host, remote provider, quorum, Byzantine consensus, secure hardware, monotonic hardware counter or provider-independent finality is claimed;
- no synthetic scaling run and no real AXM/monolith performance workload were run in Wave 123; this was a correctness/recovery gate only;
- therefore no new speed, energy, retained-compute, incremental-compute or dormant-compute result is claimed.

## Next gate

Wave 124 should bind outcome-authority rotation to the separate-process witness lineage: the old pinned witness/root must authorize the exact successor identity, the client pin must advance only after durable old-root authorization, and crash/restart tests must cut before and after each witness-root, rotation-record and client-pin publication boundary.

Negative cases should include old/new-root crossover, stale/cloned witness disks, witness rollback while the client remains newer, client-pin rollback while the witness remains newer, credential substitution, replay/truncation of the rotation tail, simultaneous old/new process views, and full witness+pin rollback retained explicitly as the surviving counterexample.

Only after that should the experiment move the witness to a genuinely separate device/host and test network partitions/reconnects. Even success there would establish only the exact tested boundary, not universal or provider-independent finality.
