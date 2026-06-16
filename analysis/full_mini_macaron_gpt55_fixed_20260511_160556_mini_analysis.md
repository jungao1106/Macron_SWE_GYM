# Mini SWE-Agent GPT-5.5 Analysis

- Job dir: `/vePFS-Mindverse/user/intern/jungao/Marcronv1_SWE/jobs/full_mini_macaron_gpt55_fixed_20260511_160556`
- Trials: 500
- Verified trials: 497
- Errors / unverified: 3 / 3
- Resolved: 385
- Resolved rate over all trials: 0.7700
- Resolved rate over verified trials: 0.7746

## Root Causes

```json
{
  "context_deadline_exceeded": 3
}
```

## Exceptions

```json
{
  "TimeoutException": 3
}
```

## Rewards

```json
{
  "1.0": 385,
  "0.0": 112
}
```

## Artifacts

- sharegpt.json: 500
- trajectory.json: 497
- mini-trajectory.json: 497

## By Project

| Project | Total | Errors | Verified | Resolved | Resolved/all | Resolved/verified |
| --- | --- | --- | --- | --- | --- | --- |
| astropy | 22 | 0 | 22 | 14 | 0.6364 | 0.6364 |
| django | 231 | 0 | 231 | 192 | 0.8312 | 0.8312 |
| matplotlib | 34 | 0 | 34 | 27 | 0.7941 | 0.7941 |
| mwaskom | 2 | 0 | 2 | 2 | 1.0000 | 1.0000 |
| pallets | 1 | 0 | 1 | 1 | 1.0000 | 1.0000 |
| psf | 8 | 0 | 8 | 7 | 0.8750 | 0.8750 |
| pydata | 22 | 1 | 21 | 15 | 0.6818 | 0.7143 |
| pylint-dev | 10 | 0 | 10 | 4 | 0.4000 | 0.4000 |
| pytest-dev | 19 | 0 | 19 | 15 | 0.7895 | 0.7895 |
| scikit-learn | 32 | 0 | 32 | 27 | 0.8438 | 0.8438 |
| sphinx-doc | 44 | 0 | 44 | 29 | 0.6591 | 0.6591 |
| sympy | 75 | 2 | 73 | 52 | 0.6933 | 0.7123 |

## Trace Lengths

- ShareGPT messages mean/median/max: 21.216 / 20.0 / 63
- ShareGPT chars mean/median/max: 58312.452 / 49134.0 / 441474
- Mini messages mean/median/max: 42.62374245472837 / 40 / 126
- Assistant responses mean/median/max: 20.281690140845072 / 19 / 62
- Bash calls mean/median/max: 20.281690140845072 / 19 / 62

## Tool Calls

- Tool call rounds min/max/mean/median: 0 / 62 / 20.16 / 18.5
- Tool calls total: 10080
- Tool calls per trial min/max/mean/median: 0 / 62 / 20.16 / 18.5
- Tool argument chars min/max/mean/median: 17 / 6729 / 340.7518849206349 / 129.0
- Tool argument tokens min/max/mean/median: 9 / 1986 / 109.44107142857143 / 44.0
- Tool observation chars min/max/mean/median: 0 / 0 / 0.0 / 0.0
- Tool observation tokens min/max/mean/median: 0 / 0 / 0.0 / 0.0
- Tool error count: 0
- Tool validation error count: 0

### Tool Counts

| Tool | Count | Arg tokens min/max/mean/median | Observation tokens min/max/mean/median |
| --- | ---: | ---: | ---: |
| bash | 10080 | 9 / 1986 / 109.44107142857143 / 44.0 | 0 / 0 / 0.0 / 0.0 |

## Tokens

- Input tokens mean/median/max: 241154.73641851108 / 158231 / 3590521
- Cached tokens mean/median/max: 128807.66197183098 / 66048 / 2205184
- Output tokens mean/median/max: 4366.519114688129 / 3645 / 18313
- Total tokens mean/median/max: 245521.2555331992 / 160856 / 3593706

## Cost

- Agent result total cost: 376.295984
- Agent result cost mean/median/max: 0.7571347766599599 / 0.602518 / 8.124827000000002
- Mini trajectory total cost: 376.295984

## Timing

- Trial seconds mean/median/max: 228.642682482 / 194.6952795 / 1367.972898

## Interpretation

- The headline all-trial resolved rate is dominated by infrastructure/configuration failures, not only model quality.
- The largest class is `artifact_write_argument_list_too_long`, which happens while writing large mini trajectories through `/bin/sh`; those runs often reached submission before Harbor marked the trial as an exception.
- `unsupported_temperature_parameter` points to the GPT-5.5/Macaron endpoint rejecting the configured `temperature` parameter.
- `auth_token_revoked` indicates a credential/session issue late in the run.
