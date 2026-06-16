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

DEFAULT_DATASET_NAME = "swe-bench/swe-bench-verified"
PINNED_SWEBENCH_VERIFIED_REF = (
    "2"
)
DEFAULT_DATASET = f"{DEFAULT_DATASET_NAME}@{PINNED_SWEBENCH_VERIFIED_REF}"
DEFAULT_PROVIDER = "novita"
DEFAULT_AGENT_TYPE = "pi"
DEFAULT_E2B_CPUS = 1
DEFAULT_E2B_MEMORY_MB = 4096
DEFAULT_E2B_STORAGE_MB = 10240


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


def _pin_dataset(value: str) -> str:
    value = value.strip()
    if value == DEFAULT_DATASET_NAME:
        return DEFAULT_DATASET
    return value


def _parse_dataset(value: str) -> tuple[str, str | None]:
    value = _pin_dataset(value)
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


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _optional_float_env(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return float(value)


def _read_task_names_file(path: str) -> list[str]:
    task_names: list[str] = []
    task_path = Path(path).expanduser()
    for line in task_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            task_names.append(line)
    return task_names


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
                "auth_header": provider.pi_auth_header,
                "model_reasoning": provider.pi_model_reasoning,
                "default_api_key": provider.default_api_key,
                "result_only": args.result_only,
                "use_skills": args.use_skills,
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

    provider = _provider_spec()
    dataset = _pin_dataset(args.dataset)
    dataset_path = Path(dataset).expanduser()

    dataset_kwargs: dict[str, Any] = {
        "n_tasks": args.n_tasks,
        "task_names": args.include_task_name or None,
        "exclude_task_names": args.exclude_task_name or None,
        "overwrite": args.overwrite_tasks,
        "download_dir": ROOT / ".cache" / "harbor_tasks",
    }
    if dataset_path.exists():
        dataset_kwargs["path"] = dataset_path.resolve()
    else:
        dataset_name, dataset_ref = _parse_dataset(dataset)
        dataset_kwargs["name"] = dataset_name
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


def _patch_harbor_runtime(*, result_only: bool = False) -> None:
    """Apply small compatibility fixes for the installed Harbor package."""
    from harbor.verifier.verifier import Verifier

    original_verify = Verifier.verify
    if getattr(original_verify, "_macaron_verifier_dir_patch", False):
        pass
    else:
        async def verify_with_local_dirs(self: Any) -> Any:
            self._trial_paths.verifier_dir.mkdir(parents=True, exist_ok=True)
            self._trial_paths.test_stdout_path.parent.mkdir(parents=True, exist_ok=True)
            return await original_verify(self)

        verify_with_local_dirs._macaron_verifier_dir_patch = True  # type: ignore[attr-defined]
        Verifier.verify = verify_with_local_dirs

    if not result_only:
        return

    from harbor.models.trial.paths import EnvironmentPaths
    from harbor.trial.trial import Trial

    original_download_logs = Trial._maybe_download_logs
    if not getattr(original_download_logs, "_macaron_result_only_patch", False):
        async def download_without_agent_logs(self: Any, source_dir: str, target_dir: Path) -> None:
            if str(source_dir) == EnvironmentPaths.agent_dir.as_posix():
                self._are_agent_logs_downloaded = True
                return
            return await original_download_logs(self, source_dir, target_dir)

        download_without_agent_logs._macaron_result_only_patch = True  # type: ignore[attr-defined]
        Trial._maybe_download_logs = download_without_agent_logs

    original_upload_logs = Trial._maybe_upload_agent_logs
    if not getattr(original_upload_logs, "_macaron_result_only_patch", False):
        async def skip_agent_log_upload(self: Any) -> None:
            return None

        skip_agent_log_upload._macaron_result_only_patch = True  # type: ignore[attr-defined]
        Trial._maybe_upload_agent_logs = skip_agent_log_upload

    original_populate_context = Trial._maybe_populate_agent_context
    if not getattr(original_populate_context, "_macaron_result_only_patch", False):
        def skip_agent_context_population(self: Any) -> None:
            return None

        skip_agent_context_population._macaron_result_only_patch = True  # type: ignore[attr-defined]
        Trial._maybe_populate_agent_context = skip_agent_context_population


async def run_job(args: argparse.Namespace) -> Path:
    from harbor.job import Job

    _patch_harbor_runtime(result_only=args.result_only)

    config = build_config(args)
    config_path = ROOT / "configs" / f"{args.job_name}.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config.model_dump_json(indent=2))

    log_file = ROOT / "logs" / f"{args.job_name}.log"
    log_file.write_text("")

    _log(f"job={args.job_name} dataset={_pin_dataset(args.dataset)}", log_file=log_file)
    _log(
        "env=e2b "
        f"agent={args.agent_type} "
        f"namespace={args.e2b_template_namespace} "
        f"pi_template_suffix={args.e2b_pi_template_suffix or '<disabled>'} "
        f"sandbox_timeout_sec={min(args.e2b_sandbox_timeout_sec, 7200)} "
        f"concurrency={args.concurrency} "
        f"cpus={args.override_cpus} "
        f"memory_mb={args.override_memory_mb} "
        f"storage_mb={args.override_storage_mb} "
        f"model={_provider_spec().model_name} "
        f"result_only={args.result_only}",
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
    parser.add_argument("--job-name", default=os.getenv("JOB_NAME"))
    parser.add_argument(
        "--provider",
        default=provider,
        help="Model provider profile from providers/specs.py, for example novita, tinker, macaron, or mindlab.",
    )
    parser.add_argument(
        "--provider-base-url",
        default=os.getenv("PROVIDER_BASE_URL"),
        help="Override <PROVIDER>_BASE_URL for this run.",
    )
    parser.add_argument(
        "--provider-model",
        default=os.getenv("PROVIDER_MODEL"),
        help="Override <PROVIDER>_MODEL for this run.",
    )
    parser.add_argument(
        "--provider-api-key",
        default=os.getenv("PROVIDER_API_KEY"),
        help="Override <PROVIDER>_API_KEY for this run.",
    )
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("E2B_CONCURRENCY", "10")))
    n_tasks_env = os.getenv("N_TASKS")
    parser.add_argument(
        "--n-tasks",
        type=int,
        default=int(n_tasks_env) if n_tasks_env else None,
    )
    parser.add_argument("--include-task-name", action="append", default=None)
    parser.add_argument(
        "--task-names-file",
        action="append",
        default=None,
        help="Read task names from a file, one task name per non-comment line. Repeatable.",
    )
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
        help="E2B sandbox timeout in seconds.",
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--debug", action="store_true")
    skills_group = parser.add_mutually_exclusive_group()
    skills_group.add_argument(
        "--use-skills",
        action="store_true",
        default=_bool_env("PI_USE_SKILLS", "false"),
        help="Package repository skills into the Pi task sandbox and include skill instructions in the prompt.",
    )
    skills_group.add_argument(
        "--no-skills",
        dest="use_skills",
        action="store_false",
        help="Do not package skills and do not include skill instructions in the Pi prompt.",
    )
    parser.add_argument(
        "--result-only",
        action="store_true",
        default=_bool_env("RESULT_ONLY"),
        help=(
            "Do not download/upload agent logs or generate local trajectories; "
            "run the verifier and keep only success/failure-style trial results."
        ),
    )
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
    parser.add_argument(
        "--override-cpus",
        type=int,
        default=int(os.getenv("E2B_OVERRIDE_CPUS", str(DEFAULT_E2B_CPUS))),
        help="Sandbox CPU override. SWE-Bench Verified task configs use 1 by default.",
    )
    parser.add_argument(
        "--override-memory-mb",
        type=int,
        default=int(os.getenv("E2B_OVERRIDE_MEMORY_MB", str(DEFAULT_E2B_MEMORY_MB))),
        help="Sandbox memory override in MiB. SWE-Bench Verified task configs use 4096 by default.",
    )
    parser.add_argument(
        "--override-storage-mb",
        type=int,
        default=int(os.getenv("E2B_OVERRIDE_STORAGE_MB", str(DEFAULT_E2B_STORAGE_MB))),
        help="Task storage override in MiB. E2B template builds expose memory/cpu in this SDK; storage is recorded in Harbor config.",
    )
    parser.add_argument("--model-context-window", type=int, default=None)
    parser.add_argument("--model-max-tokens", type=int, default=None)
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
    args = parser.parse_args()
    task_names = list(args.include_task_name or [])
    for task_names_file in args.task_names_file or []:
        task_names.extend(_read_task_names_file(task_names_file))
    args.include_task_name = list(dict.fromkeys(task_names)) or None
    resolved_provider = args.provider.strip().lower()
    if args.job_name is None:
        args.job_name = f"{args.agent_type}_{resolved_provider}_swebench_verified"
    if args.model_context_window is None:
        args.model_context_window = _provider_int_env(resolved_provider, "CONTEXT_WINDOW", "128000")
    if args.model_max_tokens is None:
        args.model_max_tokens = _provider_int_env(resolved_provider, "MAX_TOKENS", "32000")
    return args


def _apply_provider_overrides(args: argparse.Namespace) -> None:
    provider = args.provider.strip().lower()
    args.provider = provider
    os.environ["LLM_PROVIDER"] = provider
    prefix = provider.upper()
    if args.provider_base_url:
        os.environ[f"{prefix}_BASE_URL"] = args.provider_base_url
    if args.provider_model:
        os.environ[f"{prefix}_MODEL"] = args.provider_model
    if args.provider_api_key:
        os.environ[f"{prefix}_API_KEY"] = args.provider_api_key
    spec = resolve_provider(provider)
    if spec.default_api_key and not os.environ.get(spec.api_key_env):
        os.environ[spec.api_key_env] = spec.default_api_key


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    args = parse_args()
    _apply_provider_overrides(args)
    provider = _provider_spec()
    required = [
        "LLM_PROVIDER",
        *provider.required_env(),
        "E2B_API_KEY",
    ]
    _require_env(required)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    asyncio.run(run_job(args))


if __name__ == "__main__":
    main()
