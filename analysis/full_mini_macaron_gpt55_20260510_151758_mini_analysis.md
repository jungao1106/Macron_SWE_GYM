# Mini SWE-Agent GPT-5.5 Analysis

- Job dir: `Marcronv1_SWE/jobs/full_mini_macaron_gpt55_20260510_151758`
- Trials: 500
- Verified trials: 72
- Errors / unverified: 428 / 428
- Resolved: 60
- Resolved rate over all trials: 0.1200
- Resolved rate over verified trials: 0.8333

## Root Causes

```json
{
  "artifact_write_argument_list_too_long": 261,
  "unsupported_temperature_parameter": 150,
  "auth_token_revoked": 14,
  "context_deadline_exceeded": 2,
  "bad_gateway": 1
}
```

## Exceptions

```json
{
  "InvalidArgumentException": 261,
  "BadRequestError": 150,
  "AuthenticationError": 14,
  "TimeoutException": 2,
  "BadGatewayError": 1
}
```

## Rewards

```json
{
  "1.0": 60,
  "0.0": 12
}
```

## Artifacts

- sharegpt.json: 500
- trajectory.json: 333
- mini-trajectory.json: 333

## By Project

| Project | Total | Errors | Verified | Resolved | Resolved/all | Resolved/verified |
| --- | --- | --- | --- | --- | --- | --- |
| astropy | 22 | 18 | 4 | 1 | 0.0455 | 0.2500 |
| django | 231 | 197 | 34 | 29 | 0.1255 | 0.8529 |
| matplotlib | 34 | 28 | 6 | 6 | 0.1765 | 1.0000 |
| mwaskom | 2 | 2 | 0 | 0 | 0.0000 | 0.0000 |
| pallets | 1 | 0 | 1 | 1 | 1.0000 | 1.0000 |
| psf | 8 | 6 | 2 | 1 | 0.1250 | 0.5000 |
| pydata | 22 | 21 | 1 | 1 | 0.0455 | 1.0000 |
| pylint-dev | 10 | 9 | 1 | 0 | 0.0000 | 0.0000 |
| pytest-dev | 19 | 15 | 4 | 4 | 0.2105 | 1.0000 |
| scikit-learn | 32 | 26 | 6 | 6 | 0.1875 | 1.0000 |
| sphinx-doc | 44 | 43 | 1 | 1 | 0.0227 | 1.0000 |
| sympy | 75 | 63 | 12 | 10 | 0.1333 | 0.8333 |

## Trace Lengths

- ShareGPT messages mean/median/max: 14.194 / 14.0 / 64
- ShareGPT chars mean/median/max: 38794.568 / 33458.0 / 237376
- Mini messages mean/median/max: 42.51651651651652 / 38 / 128
- Assistant responses mean/median/max: 20.204204204204203 / 18 / 63
- Bash calls mean/median/max: 20.22222222222222 / 18 / 63

## Tokens

- Input tokens mean/median/max: 237214.1771771772 / 155202 / 1606321
- Cached tokens mean/median/max: 129823.51951951953 / 62464 / 1199104
- Output tokens mean/median/max: 4525.9009009009005 / 3710 / 32593
- Total tokens mean/median/max: 241740.07807807808 / 158387 / 1615063

## Cost

- Agent result total cost: 245.634811
- Agent result cost mean/median/max: 0.7376420750750751 / 0.5932910000000001 / 2.8978969999999995
- Mini trajectory total cost: 245.634811

## Timing

- Trial seconds mean/median/max: 255.37530806 / 267.3302735 / 791.78135

## Interpretation

- The headline all-trial resolved rate is dominated by infrastructure/configuration failures, not only model quality.
- The largest class is `artifact_write_argument_list_too_long`, which happens while writing large mini trajectories through `/bin/sh`; those runs often reached submission before Harbor marked the trial as an exception.
- `unsupported_temperature_parameter` points to the GPT-5.5/Macaron endpoint rejecting the configured `temperature` parameter.
- `auth_token_revoked` indicates a credential/session issue late in the run.
