from __future__ import annotations
from typing import Any
SCHEMA='axm.flowing-compute-head-storage-policy-decision/v0.1'

def decide(*,expected_updates_per_wake:float,objective:str='cpu')->dict[str,Any]:
    r=float(expected_updates_per_wake)
    if r<0: raise ValueError('expected_updates_per_wake must be non-negative')
    if objective not in ('cpu','write_bytes'): raise ValueError('objective must be cpu or write_bytes')
    if objective=='write_bytes':
        decision='content_addressed';confidence='clear';reason='wave21_content_addressed_generation_bytes_are_materially_lower'
    elif r<=8.0:
        decision='monolithic';confidence='clear';reason='wake_penalty_dominates_observed_update_savings'
    elif r>=14.0:
        decision='content_addressed';confidence='clear';reason='observed_resident_update_savings_amortize_wake_penalty'
    else:
        decision='HOLD';confidence='uncertain';reason='inside_wave21_empirical_cpu_break_even_band'
    return {'schema':SCHEMA,'decision':decision,'confidence':confidence,'objective':objective,'expected_updates_per_wake':r,'reason':reason,'calibration':{'cpu_break_even_observed_range':[8.153274371459803,13.21925191044376],'conservative_hold_band':[8.0,14.0],'generation_write_saved_percent':81.42434586110238},'truth':{'host_and_state_contract_specific':True,'write_bytes_and_cpu_are_separate_objectives':True,'hold_band_preserves_uncertainty':True,'universal_default_not_claimed':True}}
