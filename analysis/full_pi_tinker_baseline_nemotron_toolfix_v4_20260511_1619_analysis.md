# SWE-Bench Verified Analysis

- Job dir: `jobs/full_pi_tinker_baseline_nemotron_toolfix_v4_20260511_1619`
- Trials: 500
- Errors: 54
- Resolved count (reward == 1): 2
- Resolved rate: 0.0040
- Mean reward: 0.004

## Trace Lengths

- ShareGPT messages min/max/mean/median: 1 / 16 / 4.148 / 4.0
- ShareGPT chars min/max/mean/median: 789 / 50898 / 5232.224 / 3749.5
- ShareGPT tokens min/max/mean/median: 154 / 14281 / 1306.648 / 908.5
- ATIF steps min/max/mean/median: 0 / 9 / 2.912 / 3.0

## Pi

- System prompt variants: 1
- Tool call rounds min/max/mean/median: 0 / 6 / 0.28 / 0.0
- Tool calls total: 118
- Tool calls per trial min/max/mean/median: 0 / 6 / 0.236 / 0.0
- Tool argument chars min/max/mean/median: 2 / 1062 / 18.847457627118644 / 2.0
- Tool argument tokens min/max/mean/median: 1 / 337 / 6.313559322033898 / 1.0
- Tool observation chars min/max/mean/median: 54 / 6016 / 407.1694915254237 / 181.0
- Tool observation tokens min/max/mean/median: 18 / 1731 / 121.46610169491525 / 48.0
- Tool error count: 54
- Tool validation error count: 53

### Tool Counts

| Tool | Count | Arg tokens min/max/mean/median | Observation tokens min/max/mean/median |
| --- | ---: | ---: | ---: |
| ls | 45 | 1 / 7 / 1.711111111111111 / 1 | 94 / 190 / 134.11111111111111 / 129 |
| find | 27 | 1 / 15 / 3.888888888888889 / 1 | 20 / 1488 / 97.0 / 48 |
| bash | 24 | 1 / 35 / 6.5 / 1.0 | 18 / 956 / 102.125 / 48.0 |
| read | 16 | 1 / 11 / 2.0 / 1.0 | 34 / 1731 / 152.3125 / 48.0 |
| grep | 3 | 1 / 10 / 6.0 / 7 | 35 / 555 / 212.66666666666666 / 48 |
| write | 3 | 10 / 337 / 119.0 / 10 | 27 / 63 / 51.0 / 63 |

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

- Input tokens min/max/mean/median: None / None / None / None
- Output tokens min/max/mean/median: None / None / None / None
- Cache tokens min/max/mean/median: None / None / None / None

## Timing

- Trial seconds min/max/mean/median: 35.227897 / 390.080907 / 91.14410798 / 76.6266055

## Exceptions

```json
{
  "NonZeroAgentExitCodeError": 54
}
```