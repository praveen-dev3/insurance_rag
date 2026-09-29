# Week 10 Task Set D: failure injection on `c04`

Golden: status='covered', payout=13000.

## Injected fault

`_run_coverage_worker` raises `ClaimsWorkerError("HTTP 500: exclusions-worker unavailable for claim c04")` before making any call of its own - simulating the worker process itself being down, not a mid-call error. No retry logic exists anywhere in `w10d_orchestrator.py`, so this is the orchestrator's un-engineered default behaviour, not a designed fallback path.

## Clean run (baseline, no injected fault)

outcome=completed  status='covered'  exclusion_code='E-19'  payout=13000.0  grade=PASS (ok)

## Broken run (exclusions worker returns HTTP 500)

outcome=completed  status='undetermined'  exclusion_code=None  payout=0  grade=FAIL (status 'undetermined' != 'covered')
compute_payout actually called: False

Transcript (broken run):
```
[intake] get_claim('c04') -> form=HO-0304
[handoff 1] notes-summary-worker -> {'cause_of_loss': 'Water backed up through basement floor drain due to heavy rain', 'key_facts': ['Water came up through the drain, not from a supply line or appliance', 'Basement is finished', 'Sump pump with battery backup installed', 'Sump pump serviced by a technician six weeks prior, with service record on file', 'Damage includes flooring, drywall, and stored furniture'], 'notable_dates_or_durations': ['Heavy rain occurred overnight', 'Sump pump serviced six weeks ago']}
[handoff 2] exclusions-worker -> HTTP 500: exclusions-worker unavailable for claim c04
[handoff 3] synthesis -> {'claim_id': 'c04', 'coverage_status': 'undetermined', 'exclusion_code': None, 'deductible': None, 'payout': 0, 'rationale': 'Coverage determination could not be made due to a system error preventing the exclusions worker from processing claim c04.'}
```

## Verdict: the orchestrator **degraded**

The synthesis step reported the worker outage honestly - `coverage_status` reflects "no coverage decision reached" rather than fabricating one, and no payout was invented from thin air. A degraded answer, not a wrong one stated with confidence.
