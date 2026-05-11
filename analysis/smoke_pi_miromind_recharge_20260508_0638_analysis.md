# SWE-Bench Verified Analysis

- Job dir: `jobs/smoke_pi_miromind_recharge_20260508_0638`
- Trials: 1
- Errors: 0
- Resolved count (reward == 1): 0
- Resolved rate: 0.0000
- Mean reward: 0.0

## Trace Lengths

- ShareGPT messages mean/median/max: 4.0 / 4 / 4
- ShareGPT chars mean/median/max: 8724.0 / 8724 / 8724
- ATIF steps mean/median/max: 3.0 / 3 / 3

## Pi

- System prompt variants: 1
- Tool call rounds mean/median/max: 0.0 / 0 / 0
- Tool calls total: 0
- Tool calls per trial mean/median/max: 0.0 / 0 / 0
- Tool argument chars mean/median/max: None / None / None
- Tool observation chars mean/median/max: None / None / None
- Tool error count: 0

### Tool Counts

| Tool | Count | Arg chars mean/median/max | Observation chars mean/median/max |
| --- | ---: | ---: | ---: |

### Pi System Prompt

```text
You are Pi, a terminal-based software engineering agent running inside a Harbor SWE-Bench task sandbox.

Goal:
- Modify the repository in the current working directory so the benchmark issue is fixed.
- Prefer small, targeted changes. Do not change tests unless the task explicitly requires it.
- Inspect the repository before editing. Run relevant tests when practical.
- Leave the final state in the working tree; Harbor will run the verifier after you exit.

Operational constraints:
- You may use Pi's read, write, edit, bash, grep, find, and ls tools.
- Do not ask the user for clarification during benchmark execution.
- Do not exfiltrate secrets or print environment variables containing API keys.
- Keep a concise final message summarizing changed files and verification commands.

```

## Tokens

- Input tokens mean/median/max: 13263156.0 / 13263156 / 13263156
- Output tokens mean/median/max: 64827.0 / 64827 / 64827
- Cache tokens mean/median/max: None / None / None

## Timing

- Trial seconds mean/median/max: None / None / None

## Exceptions

```json
{}
```