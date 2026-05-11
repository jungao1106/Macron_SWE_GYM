# SWE-Bench Verified Analysis

- Job dir: `jobs/full_pi_novita_20260508_0356`
- Trials: 500
- Errors: 16
- Resolved count (reward == 1): 379
- Resolved rate: 0.7580
- Mean reward: 0.7625754527162978

## Trace Lengths

- ShareGPT messages min/max/mean/median: 15 / 612 / 104.284 / 66.0
- ShareGPT chars min/max/mean/median: 8398 / 476085 / 77656.186 / 47517.5
- ShareGPT tokens min/max/mean/median: 2551 / 118327 / 21374.196 / 13292.0
- ATIF steps min/max/mean/median: 10 / 383 / 64.118 / 41.0

## Pi

- System prompt variants: 1
- Tool call rounds min/max/mean/median: 4 / 228 / 39.172 / 25.0
- Tool calls total: 19586
- Tool calls per trial min/max/mean/median: 4 / 228 / 39.172 / 25.0
- Tool argument chars min/max/mean/median: 2 / 12636 / 332.3788420300214 / 95.0
- Tool argument tokens min/max/mean/median: 1 / 3066 / 95.40304298989074 / 30.0
- Tool observation chars min/max/mean/median: 0 / 6024 / 1123.3522924537936 / 635.0
- Tool observation tokens min/max/mean/median: 0 / 3893 / 298.30715817420605 / 173.0
- Tool error count: 0

### Tool Counts

| Tool | Count | Arg tokens min/max/mean/median | Observation tokens min/max/mean/median |
| --- | ---: | ---: | ---: |
| bash | 10057 | 8 / 2870 / 118.06015710450433 / 43 | 0 / 3893 / 226.14218951973749 / 115 |
| read | 4899 | 8 / 41 / 24.375382731169626 / 26 | 15 / 2578 / 515.2271892222902 / 337 |
| grep | 2487 | 8 / 65 / 22.49738640932851 / 22 | 18 / 2494 / 225.0506634499397 / 56 |
| edit | 1568 | 34 / 3066 / 299.6485969387755 / 205.0 | 48 / 2131 / 278.02232142857144 / 225.0 |
| find | 275 | 7 / 22 / 15.243636363636364 / 16 | 17 / 1660 / 62.2 / 24 |
| ls | 202 | 1 / 17 / 8.094059405940595 / 7.0 | 17 / 2024 / 141.1980198019802 / 117.0 |
| write | 98 | 21 / 1638 / 308.07142857142856 / 109.5 | 26 / 41 / 30.275510204081634 / 30.0 |

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

- Input tokens min/max/mean/median: 6014 / 485894 / 89834.172 / 59719.5
- Output tokens min/max/mean/median: 1742 / 236093 / 28710.942 / 14013.0
- Cache tokens min/max/mean/median: 50496 / 39766656 / 3235504.384 / 780800.0

## Timing

- Trial seconds min/max/mean/median: None / None / None / None

## Exceptions

```json
{
  "AgentTimeoutError": 14,
  "LocalProtocolError": 1,
  "AddTestsDirError": 1
}
```