# Neutral Compute Substrate Core v0.1 — extraction receipt

Date: 2026-09-20  
Status: **EXPERIMENTAL / NON-CANON / PR #64**

## Goal

Extract the smallest reusable Flowing Compute runtime from the large experimental PR #2 without carrying over MorphTile, monolith, witness, key-rotation or storage-specific machinery.

## Scope

The neutral package provides only:

- contract/source dependency registration;
- UPDATE_REQUIRED vs REUSE_EXACT plans;
- fail-closed unknown selectors;
- contract-local route allowlists;
- canonical JSON / byte artifact identities;
- non-authoritative staging;
- one logical current-generation pointer;
- commit, ancestor rollback and descendant reactivation receipts;
- non-canonical verified hot artifacts;
- sealed export/import with lineage validation;
- a host-facing deterministic commit pointer record.

Durable storage, fsync/database transactions, artifact stores, contract-local algorithms, network consensus, cryptographic witness authority, audit cadence and energy accounting are explicitly outside the core.

## First CI failure retained

Initial PR head `b82ffa6e76add440aa61fc041f3c4136eb7bd34c` ran workflow `35482929371`, job `106003864679`.

Result: **7/12 pass, 5/12 fail**.

Cause: the new neutral test used namespace-recursive selector `source:**`, while `selectorMatches` implemented global `**`, path-recursive `/**`, and one-star prefix matching but did not implement a general trailing `**` prefix. The snapshot contract was therefore incorrectly classified as `REUSE_EXACT` for `source:graph/...`, and dependent stage/rollback tests failed downstream.

The tests were not weakened or rewritten around the bug.

## Repair

Commit `2c2b85e83f379d26e255b577e7505ee823235e41` added general trailing-`**` prefix matching.

Commit `209afc8eb615b9b40b466d9e5e466b81e3bee1a6` added an exact regression:

`source:**` must match `source:graph/node-7`.

## Green verification

Exact repaired head: `209afc8eb615b9b40b466d9e5e466b81e3bee1a6`

GitHub Actions:

- workflow run: `35482959784`
- job: `106003952782`
- `npm test`: **12/12 pass, 0 fail**
- duration reported by Node test runner: ~63 ms

The suite includes positive and negative controls for selective invalidation, unknown-selector HOLD, route enforcement, reuse protection, stale-base rejection, hot/dormant separation, canonical/byte identity, ancestry/descendancy, recomputation with identical output identity, host commit records, and tampered/broken-lineage import rejection.

## Relationship to PR #2

PR #2 remains the experimental evidence/history constellation. This PR starts from clean main and does not rewrite, squash or canonize that research history.

The later authority/witness/key-rotation research is intentionally not included in the neutral core. It remains optional evidence for systems that truly need hostile or independent multi-authority operation.

## Truth boundary

Green unit tests prove this implementation's deterministic contract on the tested Node runtime. They do not prove performance gains, durable crash atomicity, artifact availability, distributed uniqueness, security against hostile hosts, or suitability for every AXM subsystem.
