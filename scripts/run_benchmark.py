#!/usr/bin/env python
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from providers import ProviderSpec, resolve_provider

DEFAULT_DATASET = "swe-bench/swe-bench-verified"
DEFAULT_PROVIDER = "novita"
DEFAULT_AGENT_TYPE = "pi"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log(message: str, *, log_file: Path | None = None) -> None:
    line = f"[{_utc_now()}] {message}"
    print(line, flush=True)
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a") as handle:
            handle.write(line + "\n")


def _require_env(names: list[str]) -> None:
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise SystemExit(
            "Missing required environment variables: "
            + ", ".join(missing)
            + f"\nFill them in {ROOT / '.env'} and rerun."
        )


def _parse_dataset(value: str) -> tuple[str, str | None]:
    if "@" in value:
        name, version = value.split("@", 1)
        return name, version
    return value, None


def _provider() -> str:
    return os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).strip().lower()


def _provider_spec() -> ProviderSpec:
    return resolve_provider(_provider())


def _provider_int_env(provider: str, suffix: str, default: str) -> int:
    return int(os.getenv(f"{provider.upper()}_{suffix}", default))


def _float_env(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def _optional_float_env(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return float(value)


def _agent_type() -> str:
    return os.getenv("AGENT_TYPE", DEFAULT_AGENT_TYPE).strip().lower()


def _agent_config(
    args: argparse.Namespace,
    provider: ProviderSpec,
) -> Any:
    from harbor.models.trial.config import AgentConfig

    common_kwargs = {
        "provider_name": provider.name,
        "api_key_env": provider.api_key_env,
        "base_url_env": provider.base_url_env,
        "model_env": provider.model_env,
    }
    if args.agent_type == "pi":
        return AgentConfig(
            import_path="agents.pi_novita_agent:PiNovitaAgent",
            model_name=provider.model_name,
            override_setup_timeout_sec=args.agent_setup_timeout_sec,
            override_timeout_sec=args.agent_timeout_sec,
            kwargs={
                **common_kwargs,
                "model_context_window": args.model_context_window,
                "model_max_tokens": args.model_max_tokens,
                "thinking": args.thinking,
                "tools": args.tools,
                "openai_compat": provider.pi_openai_compat,
            },
        )
    if args.agent_type == "mini":
        model_class = args.mini_model_class or provider.default_mini_model_class
        return AgentConfig(
            import_path="agents.mini_swe_agent:MiniSweAgent",
            model_name=provider.model_name,
            override_setup_timeout_sec=args.agent_setup_timeout_sec,
            override_timeout_sec=args.agent_timeout_sec,
            kwargs={
                **common_kwargs,
                "model_class": model_class,
                "cost_tracking": args.mini_cost_tracking,
                "step_limit": args.mini_step_limit,
                "cost_limit": args.mini_cost_limit,
                "command_timeout_sec": args.mini_command_timeout_sec,
                "temperature": args.temperature,
                "request_timeout_sec": args.mini_request_timeout_sec,
                "model_kwargs": provider.mini_kwargs(
                    temperature=args.temperature,
                    request_timeout_sec=args.mini_request_timeout_sec,
                ),
            },
        )
    raise ValueError(f"Unsupported agent type: {args.agent_type}")


def build_config(args: argparse.Namespace) -> Any:
    from harbor.models.job.config import DatasetConfig, JobConfig
    from harbor.models.metric.config import MetricConfig
    from harbor.models.metric.type import MetricType
    from harbor.models.trial.config import EnvironmentConfig

    dataset_name, dataset_ref = _parse_dataset(args.dataset)
    provider = _provider_spec()

    dataset_kwargs: dict[str, Any] = {
        "name": dataset_name,
        "n_tasks": args.n_tasks,
        "task_names": args.include_task_name or None,
        "exclude_task_names": args.exclude_task_name or None,
        "overwrite": args.overwrite_tasks,
        "download_dir": ROOT / ".cache" / "harbor_tasks",
    }
    if dataset_ref:
        dataset_kwargs["ref"] = dataset_ref

    return JobConfig(
        job_name=args.job_name,
        jobs_dir=ROOT / "jobs",
        n_attempts=1,
        n_concurrent_trials=args.concurrency,
        timeout_multiplier=args.timeout_multiplier,
        agent_timeout_multiplier=args.agent_timeout_multiplier,
        verifier_timeout_multiplier=args.verifier_timeout_multiplier,
        agent_setup_timeout_multiplier=args.agent_setup_timeout_multiplier,
        environment_build_timeout_multiplier=args.environment_build_timeout_multiplier,
        quiet=args.quiet,
        debug=args.debug,
        environment=EnvironmentConfig(
            import_path="environments.e2b_swebench:E2BSwebenchEnvironment",
            force_build=args.force_build,
            delete=not args.keep_sandboxes,
            override_cpus=args.override_cpus,
            override_memory_mb=args.override_memory_mb,
            override_storage_mb=args.override_storage_mb,
            env={
                "LLM_PROVIDER": "${LLM_PROVIDER}",
                **provider.env_mapping(),
            },
            kwargs={
                "template_namespace": args.e2b_template_namespace,
                "pi_template_suffix": args.e2b_pi_template_suffix,
                "strip_dockerfile_comments": not args.keep_dockerfile_comments,
                "sandbox_timeout_sec": args.e2b_sandbox_timeout_sec,
            },
        ),
        agents=[_agent_config(args, provider)],
        datasets=[DatasetConfig(**dataset_kwargs)],
        metrics=[MetricConfig(type=MetricType.MEAN)],
    )


def _trial_reward_summary(result: Any) -> str:
    if result is None or result.verifier_result is None:
        return "reward=<none>"
    rewards = result.verifier_result.rewards
    if not rewards:
        return "reward=<none>"
    return " ".join(f"{key}={value}" for key, value in rewards.items())


async def run_job(args: argparse.Namespace) -> Path:
    from harbor.job import Job

    config = build_config(args)
    config_path = ROOT / "configs" / f"{args.job_name}.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config.model_dump_json(indent=2))

    log_file = ROOT / "logs" / f"{args.job_name}.log"
    log_file.write_text("")

    _log(f"job={args.job_name} dataset={args.dataset}", log_file=log_file)
    _log(
        "env=e2b "
        f"agent={args.agent_type} "
        f"namespace={args.e2b_template_namespace} "
        f"pi_template_suffix={args.e2b_pi_template_suffix or '<disabled>'} "
        f"sandbox_timeout_sec={min(args.e2b_sandbox_timeout_sec, 3600)} "
        f"concurrency={args.concurrency} "
        f"model={_provider_spec().model_name}",
        log_file=log_file,
    )
    _log(f"config={config_path}", log_file=log_file)

    job = await Job.create(config)
    _log(f"resolved_trials={len(job)} job_dir={job.job_dir}", log_file=log_file)

    async def on_start(event: Any) -> None:
        _log(
            f"START trial={event.trial_id} task={event.task_name}",
            log_file=log_file,
        )

    async def on_environment(event: Any) -> None:
        _log(
            f"ENV trial={event.trial_id} task={event.task_name}",
            log_file=log_file,
        )

    async def on_agent(event: Any) -> None:
        _log(
            f"AGENT trial={event.trial_id} task={event.task_name}",
            log_file=log_file,
        )

    async def on_verifier(event: Any) -> None:
        _log(
            f"VERIFY trial={event.trial_id} task={event.task_name}",
            log_file=log_file,
        )

    async def on_end(event: Any) -> None:
        result = event.result
        status = "ok"
        exc = ""
        if result is not None and result.exception_info is not None:
            status = "error"
            exc = (
                f" exception={result.exception_info.exception_type}: "
                f"{result.exception_info.exception_message}"
            )
        _log(
            f"END trial={event.trial_id} task={event.task_name} status={status} "
            f"{_trial_reward_summary(result)}{exc}",
            log_file=log_file,
        )

    job.on_trial_started(on_start)
    job.on_environment_started(on_environment)
    job.on_agent_started(on_agent)
    job.on_verification_started(on_verifier)
    job.on_trial_ended(on_end)

    result = await job.run()
    _log(
        f"DONE total={result.n_total_trials} errors={result.stats.n_errors} result={job.job_dir / 'result.json'}",
        log_file=log_file,
    )
    return job.job_dir


def parse_args() -> argparse.Namespace:
    provider = _provider()
    agent_type = _agent_type()
    parser = argparse.ArgumentParser(
        description="Run SWE-Bench Verified on Harbor/E2B with selectable agents and OpenAI-compatible providers."
    )
    parser.add_argument("--dataset", default=os.getenv("HARBOR_DATASET", DEFAULT_DATASET))
    parser.add_argument(
        "--agent-type",
        choices=["pi", "mini"],
        default=agent_type,
        help="Agent adapter to run through Harbor/E2B.",
    )
    parser.add_argument(
        "--job-name",
        default=os.getenv("JOB_NAME", f"{agent_type}_{provider}_swebench_verified"),
    )
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("E2B_CONCURRENCY", "10")))
    n_tasks_env = os.getenv("N_TASKS")
    parser.add_argument(
        "--n-tasks",
        type=int,
        default=int(n_tasks_env) if n_tasks_env else None,
    )
    parser.add_argument("--include-task-name", action="append", default=None)
    parser.add_argument("--exclude-task-name", action="append", default=None)
    parser.add_argument("--overwrite-tasks", action="store_true")
    parser.add_argument("--force-build", action="store_true")
    parser.add_argument("--keep-sandboxes", action="store_true")
    parser.add_argument(
        "--e2b-template-namespace",
        default=os.getenv("E2B_TEMPLATE_NAMESPACE", "anchen1011"),
        help="E2B team namespace used for template names.",
    )
    parser.add_argument(
        "--e2b-pi-template-suffix",
        default=os.getenv("E2B_PI_TEMPLATE_SUFFIX", "pi_c6d7003a"),
        help="Prefer prebuilt Pi E2B templates ending with this suffix. Use an empty value to disable.",
    )
    parser.add_argument(
        "--keep-dockerfile-comments",
        action="store_true",
        help="Pass task Dockerfile comments through to the E2B SDK parser.",
    )
    parser.add_argument(
        "--e2b-sandbox-timeout-sec",
        type=int,
        default=int(os.getenv("E2B_SANDBOX_TIMEOUT_SEC", "3600")),
        help="E2B sandbox timeout in seconds. E2B currently caps this at 3600.",
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--timeout-multiplier", type=float, default=_float_env("TIMEOUT_MULTIPLIER", "1.0"))
    parser.add_argument("--agent-timeout-multiplier", type=float, default=_optional_float_env("AGENT_TIMEOUT_MULTIPLIER"))
    parser.add_argument("--verifier-timeout-multiplier", type=float, default=_optional_float_env("VERIFIER_TIMEOUT_MULTIPLIER"))
    parser.add_argument(
        "--agent-setup-timeout-multiplier",
        type=float,
        default=_float_env("AGENT_SETUP_TIMEOUT_MULTIPLIER", "2.0"),
    )
    parser.add_argument(
        "--environment-build-timeout-multiplier",
        type=float,
        default=_float_env("ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER", "2.0"),
    )
    parser.add_argument("--agent-setup-timeout-sec", type=float, default=_float_env("AGENT_SETUP_TIMEOUT_SEC", "1200"))
    parser.add_argument("--agent-timeout-sec", type=float, default=_optional_float_env("AGENT_TIMEOUT_SEC"))
    parser.add_argument("--override-cpus", type=int, default=None)
    parser.add_argument("--override-memory-mb", type=int, default=None)
    parser.add_argument("--override-storage-mb", type=int, default=None)
    parser.add_argument("--model-context-window", type=int, default=_provider_int_env(provider, "CONTEXT_WINDOW", "128000"))
    parser.add_argument("--model-max-tokens", type=int, default=_provider_int_env(provider, "MAX_TOKENS", "32000"))
    parser.add_argument("--thinking", default=os.getenv("PI_THINKING", "off"))
    parser.add_argument(
        "--tools",
        default=os.getenv("PI_TOOLS", "read,write,edit,bash,grep,find,ls"),
    )
    parser.add_argument(
        "--mini-model-class",
        choices=["litellm", "litellm_response", "litellm_textbased"],
        default=os.getenv("MINI_MODEL_CLASS"),
        help="mini-SWE-agent model class. Defaults to litellm_response for macaron, otherwise litellm.",
    )
    parser.add_argument(
        "--mini-cost-tracking",
        default=os.getenv("MINI_COST_TRACKING", "ignore_errors"),
    )
    parser.add_argument(
        "--mini-step-limit",
        type=int,
        default=int(os.getenv("MINI_STEP_LIMIT", "250")),
    )
    parser.add_argument(
        "--mini-cost-limit",
        type=float,
        default=float(os.getenv("MINI_COST_LIMIT", "0")),
    )
    parser.add_argument(
        "--mini-command-timeout-sec",
        type=int,
        default=int(os.getenv("MINI_COMMAND_TIMEOUT_SEC", "60")),
    )
    parser.add_argument(
        "--mini-request-timeout-sec",
        type=float,
        default=_float_env("MINI_REQUEST_TIMEOUT_SEC", "300"),
        help="Timeout in seconds for mini-SWE-agent model API calls. Use 0 to leave unset.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=float(os.getenv("MODEL_TEMPERATURE", "0")),
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    provider = _provider_spec()
    _require_env(
        [
            "LLM_PROVIDER",
            *provider.required_env(),
            "E2B_API_KEY",
        ]
    )
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    args = parse_args()
    asyncio.run(run_job(args))


if __name__ == "__main__":
    main()
