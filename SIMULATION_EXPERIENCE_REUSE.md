# Explore compute routes with repeatable workloads

Status: proposed applications of an existing method; documentation only.
Inspected source: `d622269cca0605236463fe8ef12aacc5f475a25a`.

[Shared method and measured neural example](https://github.com/mike-axiom-mir/axm-state-research/blob/main/docs/SIMULATION_AS_REUSABLE_EXPERIENCE.md).

The [state core](src/core.js) already distinguishes exact reuse from required
updates, limits routes by contract, and separates staging from commitment.
[Conformance](src/conformance.js) provides a shared observable boundary.

## First useful comparison

Use a host harness to generate seeded workloads with local edits, broad
invalidation, cold reconstruction and repeated unchanged inputs. Compare the
host's existing route choice with fixed rebuild and a candidate policy, always
using the same canonical source and reference results.

The core accepts artifact references; it does not itself compute the caller's
artifacts. A useful experiment must execute the real host derivation, compare
output identity against full recomputation, and charge setup, dependency
tracking, failed work, validation, checkpointing and recovery. Report host,
workload distribution, time and memory separately. Broad invalidation may make
rebuild cheaper.

Retain a policy only as a candidate plus its workload/provenance evidence.
Unknown selectors and disallowed routes must still refuse. Choosing a route
never changes canonical content or makes a staged generation authoritative.

## Simulated versus physical evidence

Fault models can cheaply explore interruption order. They cannot replace the
[filesystem host](docs/FILESYSTEM_HOST.md) and
[spine host](docs/FILESYSTEM_SPINE_HOST.md) crash tests on real processes and
storage. A candidate learned in simulation needs separate receiver conformance
and host measurements. This note does not implement a scheduler, change the
route allowlists, or promote the separate flowing-compute research branch.
