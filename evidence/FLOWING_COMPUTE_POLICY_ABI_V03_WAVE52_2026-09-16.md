# Flowing Compute Wave 52 — Policy ABI v0.3 / Setup-Amortization Family

Date: 2026-09-16  
Status: `EXPERIMENTAL POLICY-INTEROPERABILITY CHECKPOINT`

Wave 52 adds `setup_amortization_v1` for contracts where setup compute creates a dormant artifact that reduces later fresh-process cost.

New measured profiles:

### FrameState dormant mesh
- setup 6.872688 ms CPU;
- cold 24.660555 ms/start;
- dormant 20.690421 ms/start;
- audited dormant 20.760175 ms/start;
- break-even: 2 starts.

### Execution-Fabric capability index
- setup 724.536882 ms CPU;
- cold 161.366634 ms/start;
- dormant 0.475368 ms/start;
- audited dormant 25.636249 ms/start;
- break-even: 5 carried starts / 6 audited starts.

Policy inputs are expected fresh starts, artifact availability, and whether each start requires a full source audit. Expected future use is explicitly an estimate, not a fact.

## Preservation
Policy ABI v0.3 delegates older contracts to the preserved v0.2 dispatcher rather than reimplementing them.

Checks passed:
- 9 setup-amortization decisions;
- old FrameState manifest total 48 remains accepted; invented total 60 still HOLDs;
- old Execution Graph measured 127 affected / 82 mutated remains global; fake 127 / 8 extrapolation still HOLDs.

So adding the new evaluator did not weaken old measured-domain guards.

Truth: one dispatcher may host multiple evaluator families, but not one universal cost model. CPU-only; no hardware joule counter here; no compute/energy-from-nothing claim.
