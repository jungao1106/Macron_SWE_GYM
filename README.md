# Marcronv1 SWE-Bench Runner

Runs SWE-Bench Verified with:

- Novita, Mindlab, MiroMind, Macaron GPT 5.5, or Tinker as backend model providers.
- Pi or mini-SWE-agent as the coding agent layer.
- Harbor as the benchmark harness.
- E2B as the sandbox provider with concurrency 10 by default.
- A project-local E2B adapter that builds templates under your team namespace.
- A provider capability layer so Pi/mini agents can be combined with compatible providers without per-agent forks.

Agent traces are saved per trial under `jobs/<job>/<trial>/agent/`.

Pi traces include:

- `agent/pi-events.jsonl`: raw Pi JSON event stream.
- `agent/sharegpt.json`: ShareGPT-formatted trace.
- `agent/trajectory.json`: Harbor ATIF trajectory.
- `agent/pi-metadata.json`: model, provider, Pi system prompt, and trace metadata.

mini-SWE-agent traces include:

- `agent/mini-trajectory.json`: raw mini-SWE-agent trajectory.
- `agent/sharegpt.json`: ShareGPT-formatted trace.
- `agent/trajectory.json`: Harbor ATIF trajectory.
- `agent/mini-config.yaml`: resolved mini-SWE-agent config.
- `agent/mini-metadata.json`: model, provider, prompt, and trace metadata.

## Workflow

This repo is a thin experiment runner around Harbor. The usual flow is:

1. Configure runtime defaults in `.env`.
   This chooses the agent (`AGENT_TYPE`), model provider (`LLM_PROVIDER`), provider credentials, E2B namespace, concurrency, and default dataset. Keep `HARBOR_DATASET` pinned to a dataset revision so Harbor does not silently follow a republished `latest`.

2. Start a job with `scripts/run_benchmark.py`.
   The script loads `.env`, resolves provider capabilities from `providers/specs.py`, applies any CLI overrides such as `--job-name`, `--n-tasks`, and `--concurrency`, then builds a Harbor `JobConfig`.

3. Save the exact job config under `configs/<job-name>.json`.
   These files are run snapshots. They record the model, agent, dataset, E2B settings, timeout settings, and concurrency used for that job. They are useful for audit and reproducibility, but the normal entry point is still `scripts/run_benchmark.py`.

4. Harbor resolves SWE-Bench tasks from the dataset.
   Tasks are cached under `.cache/harbor_tasks/`. Each task contains the issue instruction, solution reference, tests, and environment Dockerfile. The default SWE-Bench Verified dataset is pinned to revision `2`, whose dataset content hash is `b934b0cc3dc800fe945eaf9f1623329db97ee3133c706d20644524c7759fb341`, so repeated runs reuse the same task refs and E2B template names.

5. Harbor creates one trial per task under `jobs/<job-name>/<trial-name>/`.
   Each trial gets its own config, sandbox, agent logs, verifier logs, result file, and trace files.

6. `environments/e2b_swebench.py` creates or reuses an E2B sandbox.
   The adapter prefers Pi-preinstalled templates ending in `__${E2B_PI_TEMPLATE_SUFFIX}`. If a matching Pi template exists, it avoids reinstalling Pi inside the sandbox. If it does not exist, it can build a task template from the task Dockerfile.

7. The configured agent runs inside the E2B sandbox.
   For `AGENT_TYPE=pi`, Harbor calls `agents.pi_novita_agent:PiNovitaAgent`, which writes Pi's provider config to `~/.pi/agent/models.json` and runs `pi --print`. For `AGENT_TYPE=mini`, Harbor calls `agents.mini_swe_agent:MiniSweAgent`, which writes a resolved mini-SWE-agent config and runs the mini CLI.

8. Harbor runs the verifier.
   The verifier checks the patched repository in the sandbox and writes rewards, stdout, reports, and the trial result.

9. Runtime progress is written to `logs/<job-name>.log` and optional shell output is written to `run_logs/<job-name>.out`.
   `scripts/monitor_benchmark_job.sh <job-name>` summarizes active progress from the job directory.

10. After the job finishes, run `scripts/analyze_results.py`.
    Analysis outputs go to `analysis/<job>_analysis.json` and `analysis/<job>_analysis.md`.

11. For Pi tool-use experiments, run `scripts/check_pi_tool_harness.py`.
    This harness checks Pi `tool_execution_start` events for required arguments
    and validation errors, and flags unparsed assistant text that tries to
    serialize tool calls without becoming Pi tool events.

The core data path looks like this:

```text
.env + CLI args
  -> scripts/run_benchmark.py
  -> configs/<job-name>.json
  -> Harbor Job
  -> .cache/harbor_tasks/<task>
  -> E2B sandbox via environments/e2b_swebench.py
  -> provider compatibility profile in providers/specs.py
  -> agent adapter in agents/
  -> jobs/<job-name>/<trial-name>/
  -> logs/<job-name>.log and run_logs/<job-name>.out
  -> analysis/<job>_analysis.*
```

## Directory Map

- `.env`: local secrets and default runtime settings. Do not commit real keys.
- `.env.example`: safe template for expected environment variables.
- `scripts/run_benchmark.py`: main Harbor/E2B runner.
- `providers/`: provider compatibility profiles shared by Pi and mini agents.
- `scripts/check_*`: provider endpoint smoke checks.
- `scripts/analyze_results.py`: summarizes Harbor/Pi jobs into JSON and Markdown.
- `scripts/analyze_mini_results.py`: summarizes mini-SWE-agent style outputs.
- `scripts/monitor_benchmark_job.sh`: lightweight progress monitor for a running job.
- `agents/`: Harbor installed-agent adapters.
- `environments/`: Harbor environment adapters, including the E2B SWE-Bench template logic.
- `configs/`: generated job config snapshots.
- `jobs/`: full trial outputs, traces, verifier reports, rewards, and final job results.
- `logs/`: structured progress logs written by `run_benchmark.py`.
- `run_logs/`: shell stdout/stderr captures when jobs are launched in the background.
- `analysis/`: post-run reports generated from `jobs/`.
- `.cache/harbor_tasks/`: downloaded and prepared SWE-Bench task bundles.
- `traces/`: standalone mini-SWE-agent traces.

## Environment

The conda environment name is `marcronv1`.

```bash
source /root/miniforge3/etc/profile.d/conda.sh
conda activate marcronv1
pip install -r requirements.txt
npm install -g @earendil-works/pi-coding-agent
```

The local `.env` contains provider, agent, and E2B keys. Use `.env.example` as the template if keys need to be rotated.

Set `AGENT_TYPE` to choose the Harbor installed-agent adapter:

- `AGENT_TYPE=pi` uses `agents.pi_novita_agent:PiNovitaAgent`.
- `AGENT_TYPE=mini` uses `agents.mini_swe_agent:MiniSweAgent`.

Set `LLM_PROVIDER` to choose the backend provider. The runner combines this with `AGENT_TYPE` through `providers/specs.py`, so the same provider value works for both Pi and mini when a compatibility profile exists:

- `LLM_PROVIDER=novita` uses `NOVITA_API_KEY`, `NOVITA_BASE_URL`, and `NOVITA_MODEL`.
- `LLM_PROVIDER=miromind` uses `MIROMIND_API_KEY`, `MIROMIND_BASE_URL`, and `MIROMIND_MODEL`.
- `LLM_PROVIDER=macaron` uses `MACARON_API_KEY`, `MACARON_BASE_URL`, and `MACARON_MODEL`.
- `LLM_PROVIDER=tinker` uses `TINKER_API_KEY`, `TINKER_BASE_URL`, and `TINKER_MODEL`.
- `LLM_PROVIDER=mindlab` uses `MINDLAB_API_KEY`, `MINDLAB_BASE_URL`, and `MINDLAB_MODEL`.

Current provider compatibility profiles:

- `novita`: GLM 5.1 path. mini defaults to `litellm_textbased`; Pi enables the OpenAI-compatible ZAI thinking-text format.
- `mindlab`: local/OpenAI-compatible GLM path. Pi uses `qwen-chat-template` thinking compatibility, so `PI_THINKING=off` sends `chat_template_kwargs.enable_thinking=false`.
- `macaron`: GPT 5.5 path. mini defaults to `litellm_response`; Pi uses `openai-responses`. Both paths target the Responses API shape.
- `tinker`: Nemotron/SFT path. mini defaults to `litellm_textbased`; Pi uses the same native tool-call harness and prompt shape as `novita`.
- `miromind`: generic OpenAI-compatible path unless overridden.

Use `MINI_MODEL_CLASS` or `--mini-model-class` only when intentionally testing a different mini-SWE-agent transport.

For MiroMind 1.7 deep research:

```bash
LLM_PROVIDER=miromind
MIROMIND_BASE_URL=https://api.miromind.ai/v1
MIROMIND_MODEL=mirothinker-1-7-deepresearch
```

For Macaron GPT 5.5:

```bash
LLM_PROVIDER=macaron
MACARON_BASE_URL=https://pi-api.macaron.xin
MACARON_MODEL=gpt-5.5
```

For Tinker baseline or sampler weights:

```bash
LLM_PROVIDER=tinker
TINKER_BASE_URL=https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1
TINKER_MODEL=nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16:peft:262144
TINKER_CONTEXT_WINDOW=262144
TINKER_MAX_TOKENS=32000
```

For Mindlab GLM 5.1 through the local OpenAI-compatible endpoint:

```bash
LLM_PROVIDER=mindlab
MINDLAB_BASE_URL=http://104.40.8.230:7777/v1
MINDLAB_MODEL=swebench-glm51-sft-r16-1epoch-20260516T0059CST-ba54e04851fe-20260518T062206Z-fp8-atom
MINDLAB_API_KEY=mindlab-local-no-auth
```

One-off provider overrides can be passed without editing `.env`:

```bash
AGENT_TYPE=pi python scripts/run_benchmark.py \
  --provider mindlab \
  --provider-base-url http://104.40.8.230:7777/v1 \
  --provider-model swebench-glm51-sft-r16-1epoch-20260516T0059CST-ba54e04851fe-20260518T062206Z-fp8-atom \
  --n-tasks 1 \
  --job-name smoke_pi_mindlab_glm51
```

Use the SFT sampler checkpoint as the test group by swapping only `TINKER_MODEL`:

```bash
TINKER_MODEL=tinker://cb03316c-2b5c-50bb-9ded-5267b1e936d7:train:0/sampler_weights/final
```

Check both Tinker models against the OpenAI-compatible completions endpoint:

```bash
python scripts/check_tinker_models.py
```

The Macaron endpoint has been configured for the OpenAI Responses API shape. For mini-SWE-agent's standalone CLI wrapper, the project config is:

```bash
configs/mini-swe-agent/macaron_gpt55.yaml
```

The unified Harbor runner uses the same settings internally when `AGENT_TYPE=mini` and `LLM_PROVIDER=macaron`: `model_class: litellm_response`, `custom_llm_provider: openai`, and `api_base: https://pi-api.macaron.xin`, matching the documented mini-SWE-agent/LiteLLM override pattern for custom OpenAI-compatible endpoints. For `AGENT_TYPE=pi`, the runner configures Pi's model entry with `api: openai-responses` and fails fast if Macaron returns without any Pi tool calls, so empty no-op traces are not counted as valid runs.

Set `E2B_TEMPLATE_NAMESPACE` to your E2B team namespace. The default in this repo is `anchen1011`; without this, SWE-Bench task names such as `swe-bench/...` can produce E2B namespace errors.

`E2B_PI_TEMPLATE_SUFFIX` defaults to `pi_c6d7003a`. When a matching template such as `anchen1011/swe-bench__sphinx-doc__sphinx-8621__469ee09b__pi_c6d7003a` already exists, the runner reuses it before trying to build a new task template.

`E2B_SANDBOX_TIMEOUT_SEC` defaults to `3600`, which is E2B's current maximum sandbox timeout.

SWE-Bench Verified task configs in this runner resolve to `cpus=1`, `memory_mb=4096`, and `storage_mb=10240`. The runner now applies those as explicit E2B override defaults through `E2B_OVERRIDE_CPUS`, `E2B_OVERRIDE_MEMORY_MB`, and `E2B_OVERRIDE_STORAGE_MB`, or via `--override-cpus`, `--override-memory-mb`, and `--override-storage-mb`. For larger batch runs where verifier installs or repo build artifacts hit resource limits, a conservative setting is `--override-memory-mb 8192 --override-storage-mb 20480`. With the current E2B Python SDK, template creation exposes CPU and memory directly; storage remains recorded in the Harbor task config and should be treated as best-effort unless E2B exposes template disk sizing in the SDK/API used here.

Timeouts are centralized in `.env` and can still be overridden on the CLI:

```bash
TIMEOUT_MULTIPLIER=1.0
AGENT_TIMEOUT_MULTIPLIER=
VERIFIER_TIMEOUT_MULTIPLIER=
AGENT_SETUP_TIMEOUT_MULTIPLIER=2.0
ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER=2.0
AGENT_SETUP_TIMEOUT_SEC=1200
AGENT_TIMEOUT_SEC=
MINI_REQUEST_TIMEOUT_SEC=300
```

The runner applies these values when building the Harbor `JobConfig`. `MINI_REQUEST_TIMEOUT_SEC` is passed into mini-SWE-agent/LiteLLM request kwargs; `--agent-timeout-sec`, `--timeout-multiplier`, and the specific multiplier flags can override the defaults for one run.

## Run

Smoke test one task first:

```bash
python scripts/run_benchmark.py --n-tasks 1 --job-name smoke_pi_miromind
```

Smoke test Pi/Tinker tool calling on a known task and gate the trace:

```bash
AGENT_TYPE=pi LLM_PROVIDER=tinker python scripts/run_benchmark.py \
  --include-task-name swe-bench/django__django-12406 \
  --job-name smoke_pi_tinker_tool_harness

python scripts/check_pi_tool_harness.py \
  --job-dir jobs/smoke_pi_tinker_tool_harness
```

Smoke test a specific agent/provider combination:

```bash
AGENT_TYPE=mini LLM_PROVIDER=novita python scripts/run_benchmark.py \
  --include-task-name swe-bench/django__django-12406 \
  --job-name smoke_mini_novita_glm51
```

Run the same Harbor/E2B pipeline with mini-SWE-agent and Macaron GPT 5.5:

```bash
AGENT_TYPE=mini LLM_PROVIDER=macaron python scripts/run_benchmark.py --n-tasks 1 --job-name smoke_mini_macaron_gpt55
```

Run the Pi agent through Harbor/E2B with Tinker:

```bash
AGENT_TYPE=pi LLM_PROVIDER=tinker TINKER_MODEL=nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16:peft:262144 python scripts/run_benchmark.py --job-name full_pi_tinker_baseline
AGENT_TYPE=pi LLM_PROVIDER=tinker TINKER_MODEL=tinker://cb03316c-2b5c-50bb-9ded-5267b1e936d7:train:0/sampler_weights/final python scripts/run_benchmark.py --job-name full_pi_tinker_sft
```

Full SWE-Bench Verified run:

```bash
python scripts/run_benchmark.py
```

Full run with a different agent/provider combination:

```bash
AGENT_TYPE=mini LLM_PROVIDER=macaron JOB_NAME=full_mini_macaron_gpt55 python scripts/run_benchmark.py
```

Full run with mini-SWE-agent and GLM 5.1:

```bash
AGENT_TYPE=mini LLM_PROVIDER=novita JOB_NAME=full_mini_novita_glm51 python scripts/run_benchmark.py
```

Smoke matrix for the currently supported 2 x 3 combinations:

```bash
for agent in mini pi; do
  for provider in novita macaron tinker; do
    AGENT_TYPE=$agent LLM_PROVIDER=$provider python scripts/run_benchmark.py \
      --include-task-name swe-bench/django__django-12406 \
      --job-name smoke_matrix_${agent}_${provider}
  done
done
```

As of 2026-05-12, the smoke matrix has returned `trajectory.json` traces for:

- `mini + novita`
- `pi + novita`
- `mini + macaron`
- `pi + macaron`
- `mini + tinker`
- `pi + tinker`

Useful options:

- `--concurrency 10`: E2B concurrent trials, default 10.
- `--e2b-template-namespace anchen1011`: E2B team namespace for template builds.
- `--e2b-pi-template-suffix pi_c6d7003a`: prefer existing Pi-preinstalled E2B templates.
- `--e2b-sandbox-timeout-sec 3600`: E2B sandbox lifetime, clamped to 3600 seconds.
- `--n-tasks N`: limit task count.
- `--include-task-name PATTERN`: run matching tasks only, repeatable.
- `--agent-timeout-sec SEC`: override agent timeout.
- `--mini-request-timeout-sec SEC`: override mini-SWE-agent/LiteLLM request timeout.
- `--timeout-multiplier FLOAT`: scale Harbor timeouts for the run.
- `--agent-timeout-multiplier FLOAT`: scale only the agent timeout.
- `--verifier-timeout-multiplier FLOAT`: scale only verifier timeouts.
- `--agent-setup-timeout-multiplier FLOAT`: scale agent setup timeout.
- `--environment-build-timeout-multiplier FLOAT`: scale E2B environment build timeout.
- `--force-build`: rebuild E2B templates.
- `--quiet`: keep Harbor UI simpler while preserving `logs/<job>.log`.

Runtime progress is written to both stdout and `logs/<job-name>.log`.

For long runs, launch in the background and monitor the job directory:

```bash
AGENT_TYPE=mini LLM_PROVIDER=novita JOB_NAME=full_mini_novita_glm51 \
  nohup python scripts/run_benchmark.py > run_logs/full_mini_novita_glm51.out 2>&1 &

scripts/monitor_benchmark_job.sh full_mini_novita_glm51
```

## mini-SWE-agent

Check the Macaron GPT 5.5 Responses endpoint without starting a SWE-Bench run:

```bash
python scripts/check_macaron_gpt55.py
```

Run mini-SWE-agent locally with the Macaron config:

```bash
scripts/run_mini_macaron_gpt55.sh --task "Inspect this repo and run a harmless smoke check." -y --exit-immediately
```

Run one SWE-Bench Verified instance with mini-SWE-agent:

```bash
scripts/run_mini_swebench_macaron_gpt55.sh
```

The SWE-Bench wrapper defaults to `--subset verified --split test --slice 0:1 --workers 1` and writes under `traces/mini_macaron_gpt55`. Override these without editing files:

```bash
MSWEA_SWEBENCH_SLICE=0:5 MSWEA_WORKERS=2 scripts/run_mini_swebench_macaron_gpt55.sh
```

To test another model supported by the same key, set `MACARON_MODEL` in `.env` or inline:

```bash
MACARON_MODEL=gpt-5.5 scripts/run_mini_macaron_gpt55.sh --task "hello" -y --exit-immediately
```

## Analyze

Analyze the latest job:

```bash
python scripts/analyze_results.py
```

Analyze a specific job:

```bash
python scripts/analyze_results.py --job-dir jobs/<job-name>
```

For mini-SWE-agent-focused reports, use:

```bash
python scripts/analyze_mini_results.py --job-dir jobs/<job-name>
```

Outputs:

- `analysis/<job>_analysis.json`
- `analysis/<job>_analysis.md`

The report includes overall performance, reward distribution, exception distribution, ShareGPT trace length, ATIF step length, system prompt, tool call rounds, token usage, and timing.

## Before Updating Code

Use this short checklist before pushing runner changes:

```bash
python -m py_compile scripts/run_benchmark.py agents/mini_swe_agent.py agents/pi_novita_agent.py providers/specs.py

AGENT_TYPE=mini LLM_PROVIDER=novita python scripts/run_benchmark.py \
  --include-task-name swe-bench/django__django-12406 \
  --job-name smoke_update_mini_novita

test -f jobs/smoke_update_mini_novita/*/agent/trajectory.json
```

If the change touches provider compatibility, rerun the 2 x 3 smoke matrix above and confirm every trial has `agent/trajectory.json` plus either `agent/pi-events.jsonl` or `agent/mini-trajectory.json`.
