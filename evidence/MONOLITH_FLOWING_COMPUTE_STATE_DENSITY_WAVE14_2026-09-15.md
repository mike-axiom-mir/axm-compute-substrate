# Flowing Compute Wave 14 — Dormant State Density vs Wake Compute

Date: 2026-09-15  
Status: `EXPERIMENTAL STORAGE/COMPUTE TRADEOFF EVIDENCE`

## Question

Can the 662 KB hardened dormant Execution Graph state from Wave 12 be made materially smaller without spending enough decode/validation compute to erase its resume advantage?

Smaller is not treated as automatically better.

## Where the bytes are

Canonical compact JSON dormant state: **662,225 bytes**.

- `edge_hashes`: ~289,441 bytes (**43.7%**)
- `edge_topology_hashes`: ~289,441 bytes (**43.7%**)
- `component_edges`: ~47,969 bytes (**7.2%**)

About **87.4%** of the JSON body is the two per-edge SHA-256 maps. Much of that storage overhead is hexadecimal/JSON representation rather than extra cryptographic information.

## Storage candidates

| format | bytes | % of JSON |
|---|---:|---:|
| canonical JSON | 662,225 | 100% |
| zlib-6 JSON | 283,820 | 42.9% |
| gzip-6 JSON | 283,832 | 42.9% |
| deterministic AXM packed (`AXDS v0.1`) | **261,570** | **39.5%** |
| LZMA JSON | 228,356 | 34.5% |

AXDS stores structural metadata in a compressed canonical header and SHA-256 digests as raw 32-byte blocks. AXDS exact semantic round-trip and container-tamper rejection both pass.

## Decode + semantic-validation CPU

31 trials, four operations/trial, median per operation:

| format | median CPU |
|---|---:|
| JSON | **6.453 ms** |
| zlib-6 JSON | 8.725 ms |
| gzip-6 JSON | 8.567 ms |
| AXDS packed | **6.961 ms** |
| LZMA JSON | 15.891 ms |

AXDS is about 7.9% slower than JSON for full decode + semantic validation while using 39.5% of the storage. Generic gzip is ~32.8% slower; LZMA is smaller but much more CPU-expensive in this test.

## Integration control — double-validation trap

The first AXDS integration verified/unpacked the container and then let the JSON-oriented transition runtime validate/canonical-hash the same reconstructed state again. That produced an apparent **31–37% CPU penalty** versus JSON. This was not a fair format comparison because AXDS paid two validation boundaries.

## Fair single-validation handoff control

A research-only control treated successful `unpack_state(..., verify_semantic_hash=True)` as the one semantic validation and skipped the redundant second validation inside the transition runtime.

11 alternating fresh-process trials per format/case:

### 58/127 affected

- JSON transition: **14.687 ms CPU**
- AXDS single-validation: **15.686 ms**
- AXDS delta: **+6.8% CPU**

### 127/127 affected

- JSON transition: **17.464 ms CPU**
- AXDS single-validation: **17.523 ms**
- AXDS delta: **+0.33% CPU**

Exact final state hashes passed.

For comparison, gzip integration cost about **+19.4% CPU** at 58/127 and **+14.5%** at 127/127 versus JSON.

## Result

AXDS v0.1 is **not promoted as the runtime format yet**, but it survives the first density test:

- ~60.5% storage reduction versus canonical JSON;
- exact semantic round-trip;
- tamper detection;
- single-validation transition CPU within ~0–7% of JSON in the measured cases;
- materially better transition CPU than generic gzip in these tests.

The remaining problem is API truth: the runtime needs a first-class **validated-state handoff** so it can accept state that was already semantically verified without trusting an arbitrary object or hashing the same state twice.

## Truth boundary

- AXDS v0.1 reconstructs Python dictionaries/hex strings before the existing updater; it is not a native packed execution engine.
- The single-validation integration used a research-only bypass after successful semantic validation; that bypass is not a production trust boundary.
- LZMA is smaller than AXDS in this test.
- Storage/CPU results are one host / one state body.
- No claim that AXDS is globally optimal.

## Next gate

Build a validated-state handoff contract whose validator returns bounded evidence the transition runtime can consume once, preserving validation identity while preventing accidental double validation and refusing unvalidated state.
