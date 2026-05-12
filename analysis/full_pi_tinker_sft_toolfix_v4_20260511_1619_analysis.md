# SWE-Bench Verified Analysis

- Job dir: `jobs/full_pi_tinker_sft_toolfix_v4_20260511_1619`
- Trials: 500
- Errors: 54
- Resolved count (reward == 1): 3
- Resolved rate: 0.0060
- Mean reward: 0.006

## Trace Lengths

- ShareGPT messages min/max/mean/median: 1 / 474 / 9.042 / 7.0
- ShareGPT chars min/max/mean/median: 789 / 260454 / 7791.876 / 5194.5
- ShareGPT tokens min/max/mean/median: 154 / 72593 / 2044.784 / 1341.0
- ATIF steps min/max/mean/median: 0 / 240 / 5.922 / 5.0

## Pi

- System prompt variants: 1
- Tool call rounds min/max/mean/median: 0 / 233 / 2.164 / 1.0
- Tool calls total: 1060
- Tool calls per trial min/max/mean/median: 0 / 233 / 2.12 / 1.0
- Tool argument chars min/max/mean/median: 2 / 1632 / 61.781132075471696 / 57.5
- Tool argument tokens min/max/mean/median: 1 / 464 / 20.189622641509434 / 19.0
- Tool observation chars min/max/mean/median: 53 / 6016 / 1190.9254716981131 / 181.0
- Tool observation tokens min/max/mean/median: 18 / 2698 / 320.53207547169814 / 48.0
- Tool error count: 468
- Tool validation error count: 267

### Tool Counts

| Tool | Count | Arg tokens min/max/mean/median | Observation tokens min/max/mean/median |
| --- | ---: | ---: | ---: |
| grep | 308 | 1 / 67 / 22.603896103896105 / 22.0 | 18 / 2698 / 396.3344155844156 / 58.0 |
| bash | 308 | 1 / 88 / 17.454545454545453 / 11.5 | 18 / 2116 / 175.01623376623377 / 48.0 |
| read | 275 | 1 / 38 / 21.96 / 27 | 34 / 1863 / 442.08363636363634 / 49 |
| find | 109 | 1 / 35 / 13.18348623853211 / 13 | 18 / 1751 / 316.0183486238532 / 47 |
| ls | 47 | 1 / 21 / 5.468085106382978 / 5 | 29 / 167 / 120.23404255319149 / 123 |
| edit | 9 | 12 / 340 / 79.22222222222223 / 14 | 64 / 427 / 138.77777777777777 / 67 |
| write | 4 | 16 / 464 / 154.25 / 68.5 | 27 / 620 / 217.25 / 111.0 |

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

- Trial seconds min/max/mean/median: 41.175838 / 682.225094 / 91.469129476 / 75.33353550000001

## Exceptions

```json
{
  "NonZeroAgentExitCodeError": 54
}
```