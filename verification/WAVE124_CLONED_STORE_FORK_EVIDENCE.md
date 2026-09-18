# Independent verification — Wave 124 cloned-store credential fork

Status: **FAIL at the cloned-store/directory-identity next gate; Wave 124's bounded same-directory flock repair still survives.**

Lane: `verifier/wave124-cloned-store-fork`  
PR: **#49 — draft / unmerged / NON-CANON**  
Builder evidence head read before the test: `27ccee01297feaa9dac169a00d6af456979f606b`  
Builder exact tested source: `959e4c46e7c2ecf8e2043ebaa177b696d7d35f31`

## Builder result independently rerun

The untouched Wave 124 self-test was rerun from the verifier branch before the attack:

- normal Python: **13/13 PASS**
- `python -O`: **13/13 PASS**

This confirms the intended same-directory exclusive-store lease repair still works within Wave 124's stated boundary.

## Counterexample

`FAIL_CLONED_WITNESS_STORE_FORKS_ONE_PINNED_CREDENTIAL_INTO_CONTRADICTORY_VALID_HISTORIES`

The verifier started one genuine Wave 124 server, wrote one genuine authenticated HOLD record, then copied the live witness directory byte-for-byte to a second directory. The copy preserved the exact root, credential and ledger prefix, but necessarily created a different `serve.lock` inode. A second unchanged Wave 124 server therefore acquired the cloned lease and served concurrently.

For one exact `(authority_sha, transition_sha)`, the original server accepted stable `COMMIT` while the cloned server accepted stable `REJECT`.

The important result is stronger than the prior shared-file Wave 123 race:

- both servers stayed live at the same time;
- both exposed the **same pinned credential fingerprint**;
- the cloned prefix was byte-identical to the original prefix;
- the contradictory terminal rows occupied the **same sequence 2**;
- both terminal rows pointed to the **same predecessor record SHA**;
- the signed terminal record SHAs differed, as expected for COMMIT vs REJECT;
- the original ledger independently verified with 2 valid rows;
- the cloned ledger independently verified with 2 valid rows;
- the normal local-receipt primitive retained the COMMIT receipt as valid;
- a second normal local-receipt journal retained the REJECT receipt as valid.

So later validation does **not** necessarily collapse this fork into a corrupt ledger. Each branch can remain internally valid while presenting contradictory authenticated terminal truth under one copied credential identity.

The counterexample reproduced under both ordinary Python and `python -O`.

## Exact CI evidence

Verifier code/workflow head tested: `8a64415d9d2e93dc405e254fb2bc04be5841093e`

GitHub Actions:

- run: `35290554124`
- job: `105432237732`
- conclusion: **success**
- artifact: `10526255184` (`wave124-cloned-store-fork-verifier`)
- artifact size: `8731` bytes
- artifact SHA-256: `00c75622e0902114fba5acb81c87b0eb24e826a78bd03035fe5a3e407f7a8ad3`

The artifact contains the untouched Wave 124 normal/optimized reports, the normal/optimized adversarial reports, and a source-identity record.

Source identities challenged:

- Wave 124 tool blob: `d8ececaab8aedd3ca9543b36c5e90d9130d19905`
- Wave 124 self-test blob: `c2a916feebb3026a434cd0f25eb777efb0729bd4`

## Truth boundary

This test intentionally crosses the boundary Wave 124 already names as unproved. It does **not** falsify its same-directory `flock` exclusion result. It uses no credential forgery, signature forgery, hash collision, prior-record rewrite, direct ledger edit after the fork, stale authority takeover, or physical power/device fault.

It also makes no speed, energy, retained-compute, incremental-compute, dormant-compute, network/provider-independence, merge, or CANON claim.

## Next adversarial gate

Do not treat a lock located inside the copyable witness store as proof of unique witness identity. On one host, bind exclusivity to a host-scoped authority identity that survives path/inode cloning (for example a trusted lease namespace keyed by the pinned credential/root identity), and make the live server use an opened store handle or equivalent path-identity check so directory replacement cannot silently redirect its later reads/writes.

Then attack:

1. exact cloned store on a second path/socket;
2. rename/swap of the live witness directory while established clients remain connected;
3. clone before and after a terminal record;
4. old and new clients observing different forks;
5. restart after `SIGKILL` with stale path metadata;
6. clone plus legitimate credential/referee rotation;
7. whole-state rollback including any host-local pin that is still copyable.

Only after one credential identity cannot be live in two divergent histories on the same claimed authority boundary should process-boundary referee rotation be promoted further.
