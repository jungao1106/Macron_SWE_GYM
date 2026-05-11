# Marcronv1 SWE-Bench Runner

Runs SWE-Bench Verified with:

- Novita, MiroMind, Macaron GPT 5.5, or Tinker as backend model providers.
- Pi or mini-SWE-agent as the coding agent layer.
- Harbor as the benchmark harness.
- E2B as the sandbox provider with concurrency 10 by default.
- A project-local E2B adapter that builds templates under your team namespace.

Agent traces are saved per trial as:

- `agent/pi-events.jsonl`: raw Pi JSON event stream.
- `agent/sharegpt.json`: ShareGPT-formatted trace.
- `agent/trajectory.json`: Harbor ATIF trajectory.
- `agent/pi-metadata.json`: model, provider, Pi system prompt, and trace metadata.

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

Set `LLM_PROVIDER` to choose the backend while keeping the same Pi agent:

- `LLM_PROVIDER=novita` uses `NOVITA_API_KEY`, `NOVITA_BASE_URL`, and `NOVITA_MODEL`.
- `LLM_PROVIDER=miromind` uses `MIROMIND_API_KEY`, `MIROMIND_BASE_URL`, and `MIROMIND_MODEL`.
- `LLM_PROVIDER=macaron` uses `MACARON_API_KEY`, `MACARON_BASE_URL`, and `MACARON_MODEL`.
- `LLM_PROVIDER=tinker` uses `TINKER_API_KEY`, `TINKER_BASE_URL`, and `TINKER_MODEL`.

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

The unified Harbor runner uses the same settings internally when `AGENT_TYPE=mini` and `LLM_PROVIDER=macaron`: `model_class: litellm_response`, `custom_llm_provider: openai`, and `api_base: https://pi-api.macaron.xin`, matching the documented mini-SWE-agent/LiteLLM override pattern for custom OpenAI-compatible endpoints.

Set `E2B_TEMPLATE_NAMESPACE` to your E2B team namespace. The default in this repo is `anchen1011`; without this, SWE-Bench task names such as `swe-bench/...` can produce E2B namespace errors.

`E2B_PI_TEMPLATE_SUFFIX` defaults to `pi_c6d7003a`. When a matching template such as `anchen1011/swe-bench__sphinx-doc__sphinx-8621__469ee09b__pi_c6d7003a` already exists, the runner reuses it before trying to build a new task template.

`E2B_SANDBOX_TIMEOUT_SEC` defaults to `3600`, which is E2B's current maximum sandbox timeout.

## Run

Smoke test one task first:

```bash
python scripts/run_benchmark.py --n-tasks 1 --job-name smoke_pi_miromind
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

Useful options:

- `--concurrency 10`: E2B concurrent trials, default 10.
- `--e2b-template-namespace anchen1011`: E2B team namespace for template builds.
- `--e2b-pi-template-suffix pi_c6d7003a`: prefer existing Pi-preinstalled E2B templates.
- `--e2b-sandbox-timeout-sec 3600`: E2B sandbox lifetime, clamped to 3600 seconds.
- `--n-tasks N`: limit task count.
- `--include-task-name PATTERN`: run matching tasks only, repeatable.
- `--agent-timeout-sec SEC`: override agent timeout.
- `--force-build`: rebuild E2B templates.
- `--quiet`: keep Harbor UI simpler while preserving `logs/<job>.log`.

Runtime progress is written to both stdout and `logs/<job-name>.log`.

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

Outputs:

- `analysis/<job>_analysis.json`
- `analysis/<job>_analysis.md`

The report includes overall performance, reward distribution, exception distribution, ShareGPT trace length, ATIF step length, Pi system prompt, tool call rounds, token usage, and timing.
