#!/usr/bin/env python
import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def duration_sec(start: str | None, end: str | None) -> float | None:
    start_dt = parse_dt(start)
    end_dt = parse_dt(end)
    if start_dt is None or end_dt is None:
        return None
    return (end_dt - start_dt).total_seconds()


def summarize(values: list[float] | list[int]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def _token_count(value: Any) -> int:
    text = str(value or "")
    if not text:
        return 0
    return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))


def pct(value: int, total: int) -> float:
    return value / total if total else 0.0


def project_name(task_name: str | None) -> str:
    if not task_name:
        return "unknown"
    task = task_name.removeprefix("swe-bench/")
    return task.split("__", 1)[0]


def classify_exception(exception_type: str | None, message: str | None) -> str | None:
    if not exception_type:
        return None
    msg = message or ""
    if "argument list too long" in msg:
        return "artifact_write_argument_list_too_long"
    if "Unsupported parameter: temperature" in msg:
        return "unsupported_temperature_parameter"
    if "token_revoked" in msg or "invalidated oauth token" in msg:
        return "auth_token_revoked"
    if "context deadline exceeded" in msg:
        return "context_deadline_exceeded"
    if "Bad Gateway" in msg or "502" in msg:
        return "bad_gateway"
    return exception_type


def trajectory_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "messages": 0,
            "assistant_responses": 0,
            "tool_outputs": 0,
            "bash_calls": 0,
            "input_tokens": 0,
            "cached_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0,
        }
    data = load_json(path)
    messages = data.get("messages") or []
    assistant_responses = 0
    tool_outputs = 0
    bash_calls = 0
    input_tokens = 0
    cached_tokens = 0
    output_tokens = 0
    total_tokens = 0
    cost = 0.0

    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("type") == "function_call_output":
            tool_outputs += 1
        if message.get("object") == "response":
            assistant_responses += 1
            usage = message.get("usage") or {}
            input_tokens += int(usage.get("input_tokens") or 0)
            output_tokens += int(usage.get("output_tokens") or 0)
            total_tokens += int(usage.get("total_tokens") or 0)
            details = usage.get("input_tokens_details") or {}
            cached_tokens += int(details.get("cached_tokens") or 0)
            extra = message.get("extra") or {}
            cost += float(extra.get("cost") or 0.0)
            for output in message.get("output") or []:
                if isinstance(output, dict) and output.get("name") == "bash":
                    bash_calls += 1

    return {
        "exists": True,
        "messages": len(messages),
        "assistant_responses": assistant_responses,
        "tool_outputs": tool_outputs,
        "bash_calls": bash_calls,
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cost": cost,
    }


def parse_json_arguments(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def mini_tool_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "tool_call_rounds": 0,
            "tool_calls": [],
            "tool_error_count": 0,
            "tool_validation_error_count": 0,
            "tool_name_counts": {},
            "tool_argument_chars": summarize([]),
            "tool_argument_tokens": summarize([]),
            "tool_observation_chars": summarize([]),
            "tool_observation_tokens": summarize([]),
            "tool_name_stats": {},
        }

    data = load_json(path)
    messages = data.get("messages") or []
    observations_by_call_id: dict[str, str] = {}
    tool_calls: list[dict[str, Any]] = []
    tool_call_rounds = 0
    tool_error_count = 0
    tool_validation_error_count = 0
    tool_name_counts = Counter()
    tool_argument_chars: list[int] = []
    tool_argument_tokens: list[int] = []
    tool_observation_chars: list[int] = []
    tool_observation_tokens: list[int] = []
    tool_name_argument_chars: dict[str, list[int]] = defaultdict(list)
    tool_name_argument_tokens: dict[str, list[int]] = defaultdict(list)
    tool_name_observation_chars: dict[str, list[int]] = defaultdict(list)
    tool_name_observation_tokens: dict[str, list[int]] = defaultdict(list)

    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("type") == "function_call_output":
            call_id = str(message.get("call_id") or "")
            extra = message.get("extra") if isinstance(message.get("extra"), dict) else {}
            output_text = str(message.get("output") or extra.get("raw_output") or "")
            if call_id:
                observations_by_call_id[call_id] = output_text
            continue
        if message.get("object") != "response":
            continue

        outputs = message.get("output") or []
        function_calls = [
            output
            for output in outputs
            if isinstance(output, dict) and output.get("type") == "function_call"
        ]
        if function_calls:
            tool_call_rounds += 1

        for call in function_calls:
            name = str(call.get("name") or "unknown")
            arguments = parse_json_arguments(call.get("arguments"))
            argument_text = (
                json.dumps(arguments, ensure_ascii=False)
                if arguments is not None
                else str(call.get("arguments") or "")
            )
            call_id = str(call.get("call_id") or "")
            observation_text = observations_by_call_id.get(call_id, "")
            arg_chars = len(argument_text)
            arg_tokens = _token_count(argument_text)
            obs_chars = len(observation_text)
            obs_tokens = _token_count(observation_text)
            is_error = "[error]" in observation_text or "Validation failed for tool" in observation_text
            is_validation_error = "Validation failed for tool" in observation_text

            tool_name_counts[name] += 1
            tool_argument_chars.append(arg_chars)
            tool_argument_tokens.append(arg_tokens)
            tool_observation_chars.append(obs_chars)
            tool_observation_tokens.append(obs_tokens)
            tool_name_argument_chars[name].append(arg_chars)
            tool_name_argument_tokens[name].append(arg_tokens)
            tool_name_observation_chars[name].append(obs_chars)
            tool_name_observation_tokens[name].append(obs_tokens)

            if is_error:
                tool_error_count += 1
            if is_validation_error:
                tool_validation_error_count += 1

            tool_calls.append(
                {
                    "name": name,
                    "argument_chars": arg_chars,
                    "argument_tokens": arg_tokens,
                    "observation_chars": obs_chars,
                    "observation_tokens": obs_tokens,
                    "is_error": is_error,
                    "is_validation_error": is_validation_error,
                }
            )

    return {
        "exists": True,
        "tool_call_rounds": tool_call_rounds,
        "tool_calls": tool_calls,
        "tool_error_count": tool_error_count,
        "tool_validation_error_count": tool_validation_error_count,
        "tool_name_counts": dict(tool_name_counts.most_common()),
        "tool_argument_chars": summarize(tool_argument_chars),
        "tool_argument_tokens": summarize(tool_argument_tokens),
        "tool_observation_chars": summarize(tool_observation_chars),
        "tool_observation_tokens": summarize(tool_observation_tokens),
        "tool_name_stats": {
            name: {
                "count": count,
                "argument_chars": summarize(tool_name_argument_chars[name]),
                "argument_tokens": summarize(tool_name_argument_tokens[name]),
                "observation_chars": summarize(tool_name_observation_chars[name]),
                "observation_tokens": summarize(tool_name_observation_tokens[name]),
            }
            for name, count in tool_name_counts.most_common()
        },
    }


def analyze(job_dir: Path) -> dict[str, Any]:
    job_result = load_json(job_dir / "result.json")
    trial_paths = sorted(path for path in job_dir.glob("*/result.json"))

    trials: list[dict[str, Any]] = []
    exceptions = Counter()
    root_causes = Counter()
    reward_counts = Counter()
    projects: dict[str, Counter] = defaultdict(Counter)
    durations: list[float] = []
    costs: list[float] = []
    sharegpt_messages: list[int] = []
    sharegpt_chars: list[int] = []
    mini_messages: list[int] = []
    assistant_responses: list[int] = []
    bash_calls: list[int] = []
    tool_call_rounds: list[int] = []
    tool_calls_per_trial: list[int] = []
    tool_argument_chars: list[int] = []
    tool_argument_tokens: list[int] = []
    tool_observation_chars: list[int] = []
    tool_observation_tokens: list[int] = []
    tool_name_counts = Counter()
    tool_name_argument_chars: dict[str, list[int]] = defaultdict(list)
    tool_name_argument_tokens: dict[str, list[int]] = defaultdict(list)
    tool_name_observation_chars: dict[str, list[int]] = defaultdict(list)
    tool_name_observation_tokens: dict[str, list[int]] = defaultdict(list)
    tool_error_count = 0
    tool_validation_error_count = 0
    input_tokens: list[int] = []
    cached_tokens: list[int] = []
    output_tokens: list[int] = []
    total_tokens: list[int] = []
    trajectory_costs: list[float] = []
    artifact_counts = Counter()

    for path in trial_paths:
        result = load_json(path)
        trial_dir = path.parent
        exception = result.get("exception_info") or {}
        exception_type = exception.get("exception_type")
        exception_message = exception.get("exception_message")
        root_cause = classify_exception(exception_type, exception_message)
        verifier_result = result.get("verifier_result") or {}
        rewards = verifier_result.get("rewards") or {}
        reward = rewards.get("reward")
        project = project_name(result.get("task_name"))
        agent_result = result.get("agent_result") or {}
        metadata = agent_result.get("metadata") or {}
        duration = duration_sec(result.get("started_at"), result.get("finished_at"))
        cost = agent_result.get("cost_usd")
        mini_path = trial_dir / "agent" / "mini-trajectory.json"
        sharegpt_path = trial_dir / "agent" / "sharegpt.json"
        trajectory_path = trial_dir / "agent" / "trajectory.json"
        mini_stats = trajectory_stats(mini_path)
        tool_stats = mini_tool_stats(mini_path)

        projects[project]["total"] += 1
        if exception_type:
            exceptions[exception_type] += 1
            projects[project]["errors"] += 1
        if root_cause:
            root_causes[root_cause] += 1
        if reward is not None:
            reward_counts[str(reward)] += 1
            projects[project]["verified"] += 1
            if float(reward) == 1.0:
                projects[project]["resolved"] += 1
        if duration is not None:
            durations.append(duration)
        if cost is not None:
            costs.append(float(cost))
        if metadata.get("sharegpt_trace_messages") is not None:
            sharegpt_messages.append(int(metadata["sharegpt_trace_messages"]))
        if metadata.get("sharegpt_trace_chars") is not None:
            sharegpt_chars.append(int(metadata["sharegpt_trace_chars"]))
        if mini_path.exists():
            artifact_counts["mini_trajectory"] += 1
        if sharegpt_path.exists():
            artifact_counts["sharegpt"] += 1
        if trajectory_path.exists():
            artifact_counts["trajectory"] += 1
        if mini_stats["exists"]:
            mini_messages.append(int(mini_stats["messages"]))
            assistant_responses.append(int(mini_stats["assistant_responses"]))
            bash_calls.append(int(mini_stats["bash_calls"]))
            input_tokens.append(int(mini_stats["input_tokens"]))
            cached_tokens.append(int(mini_stats["cached_tokens"]))
            output_tokens.append(int(mini_stats["output_tokens"]))
            total_tokens.append(int(mini_stats["total_tokens"]))
            trajectory_costs.append(float(mini_stats["cost"]))
        if tool_stats["exists"]:
            tool_call_rounds.append(int(tool_stats["tool_call_rounds"]))
            calls = tool_stats["tool_calls"] or []
            tool_calls_per_trial.append(len(calls))
            tool_error_count += int(tool_stats["tool_error_count"])
            tool_validation_error_count += int(tool_stats["tool_validation_error_count"])
            for name, count in (tool_stats["tool_name_counts"] or {}).items():
                tool_name_counts[name] += int(count)
            for tool_call in calls:
                name = str(tool_call.get("name") or "unknown")
                tool_argument_chars.append(int(tool_call.get("argument_chars") or 0))
                tool_argument_tokens.append(int(tool_call.get("argument_tokens") or 0))
                tool_observation_chars.append(int(tool_call.get("observation_chars") or 0))
                tool_observation_tokens.append(int(tool_call.get("observation_tokens") or 0))
                tool_name_argument_chars[name].append(int(tool_call.get("argument_chars") or 0))
                tool_name_argument_tokens[name].append(int(tool_call.get("argument_tokens") or 0))
                tool_name_observation_chars[name].append(int(tool_call.get("observation_chars") or 0))
                tool_name_observation_tokens[name].append(int(tool_call.get("observation_tokens") or 0))
        else:
            tool_call_rounds.append(0)
            tool_calls_per_trial.append(0)

        trials.append(
            {
                "trial_name": result.get("trial_name"),
                "task_name": result.get("task_name"),
                "project": project,
                "reward": reward,
                "exception_type": exception_type,
                "root_cause": root_cause,
                "duration_sec": duration,
                "cost_usd": cost,
                "sharegpt_trace_messages": metadata.get("sharegpt_trace_messages"),
                "sharegpt_trace_chars": metadata.get("sharegpt_trace_chars"),
                "mini_trajectory_exists": mini_path.exists(),
                "mini_messages": mini_stats["messages"],
                "mini_bash_calls": mini_stats["bash_calls"],
                "mini_tool_call_rounds": tool_stats["tool_call_rounds"],
                "mini_tool_calls": len(tool_stats["tool_calls"] or []),
                "mini_total_tokens": mini_stats["total_tokens"],
            }
        )

    total = len(trials)
    errors = sum(exceptions.values())
    verified = sum(reward_counts.values())
    resolved = reward_counts["1"] + reward_counts["1.0"]

    project_summary = {}
    for name, counter in sorted(projects.items()):
        project_total = counter["total"]
        project_verified = counter["verified"]
        project_resolved = counter["resolved"]
        project_summary[name] = {
            "total": project_total,
            "errors": counter["errors"],
            "verified": project_verified,
            "resolved": project_resolved,
            "resolved_rate_all": pct(project_resolved, project_total),
            "resolved_rate_verified": pct(project_resolved, project_verified),
        }

    return {
        "job_dir": str(job_dir),
        "job_result": job_result,
        "performance": {
            "total_trials": total,
            "errors": errors,
            "verified_trials": verified,
            "unverified_trials": total - verified,
            "resolved": resolved,
            "failed_verified": verified - resolved,
            "resolved_rate_all": pct(resolved, total),
            "resolved_rate_verified": pct(resolved, verified),
            "exception_distribution": dict(exceptions.most_common()),
            "root_cause_distribution": dict(root_causes.most_common()),
            "reward_distribution": dict(reward_counts.most_common()),
        },
        "artifacts": {
            "sharegpt": artifact_counts["sharegpt"],
            "trajectory": artifact_counts["trajectory"],
            "mini_trajectory": artifact_counts["mini_trajectory"],
        },
        "project_summary": project_summary,
        "trace_lengths": {
            "sharegpt_messages": summarize(sharegpt_messages),
            "sharegpt_chars": summarize(sharegpt_chars),
            "mini_messages": summarize(mini_messages),
            "assistant_responses": summarize(assistant_responses),
            "bash_calls": summarize(bash_calls),
            "tool_call_rounds": summarize(tool_call_rounds),
            "tool_calls": summarize(tool_calls_per_trial),
        },
        "tool_calls": {
            "tool_call_rounds": summarize(tool_call_rounds),
            "tool_calls_per_trial": summarize(tool_calls_per_trial),
            "tool_calls_total": sum(tool_calls_per_trial),
            "tool_error_count": tool_error_count,
            "tool_validation_error_count": tool_validation_error_count,
            "tool_name_counts": dict(tool_name_counts.most_common()),
            "tool_argument_chars": summarize(tool_argument_chars),
            "tool_argument_tokens": summarize(tool_argument_tokens),
            "tool_observation_chars": summarize(tool_observation_chars),
            "tool_observation_tokens": summarize(tool_observation_tokens),
            "tool_name_stats": {
                name: {
                    "count": count,
                    "argument_chars": summarize(tool_name_argument_chars[name]),
                    "argument_tokens": summarize(tool_name_argument_tokens[name]),
                    "observation_chars": summarize(tool_name_observation_chars[name]),
                    "observation_tokens": summarize(tool_name_observation_tokens[name]),
                }
                for name, count in tool_name_counts.most_common()
            },
        },
        "tokens": {
            "input": summarize(input_tokens),
            "cached": summarize(cached_tokens),
            "output": summarize(output_tokens),
            "total": summarize(total_tokens),
        },
        "costs": {
            "agent_result_cost_usd": summarize(costs),
            "agent_result_cost_usd_total": sum(costs),
            "mini_trajectory_cost_usd": summarize(trajectory_costs),
            "mini_trajectory_cost_usd_total": sum(trajectory_costs),
        },
        "timing": {
            "trial_duration_sec": summarize(durations),
        },
        "trials": trials,
    }


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def write_markdown(report: dict[str, Any], path: Path) -> None:
    perf = report["performance"]
    artifacts = report["artifacts"]
    traces = report["trace_lengths"]
    tool_calls = report["tool_calls"]
    tokens = report["tokens"]
    costs = report["costs"]
    timing = report["timing"]

    def stat_text(stats: dict[str, Any]) -> str:
        return f"{stats['min']} / {stats['max']} / {stats['mean']} / {stats['median']}"

    project_rows = []
    for name, stats in report["project_summary"].items():
        project_rows.append(
            [
                name,
                str(stats["total"]),
                str(stats["errors"]),
                str(stats["verified"]),
                str(stats["resolved"]),
                f"{stats['resolved_rate_all']:.4f}",
                f"{stats['resolved_rate_verified']:.4f}",
            ]
        )

    lines = [
        "# Mini SWE-Agent GPT-5.5 Analysis",
        "",
        f"- Job dir: `{report['job_dir']}`",
        f"- Trials: {perf['total_trials']}",
        f"- Verified trials: {perf['verified_trials']}",
        f"- Errors / unverified: {perf['errors']} / {perf['unverified_trials']}",
        f"- Resolved: {perf['resolved']}",
        f"- Resolved rate over all trials: {perf['resolved_rate_all']:.4f}",
        f"- Resolved rate over verified trials: {perf['resolved_rate_verified']:.4f}",
        "",
        "## Root Causes",
        "",
        "```json",
        json.dumps(perf["root_cause_distribution"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Exceptions",
        "",
        "```json",
        json.dumps(perf["exception_distribution"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Rewards",
        "",
        "```json",
        json.dumps(perf["reward_distribution"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Artifacts",
        "",
        f"- sharegpt.json: {artifacts['sharegpt']}",
        f"- trajectory.json: {artifacts['trajectory']}",
        f"- mini-trajectory.json: {artifacts['mini_trajectory']}",
        "",
        "## By Project",
        "",
        *table(
            [
                "Project",
                "Total",
                "Errors",
                "Verified",
                "Resolved",
                "Resolved/all",
                "Resolved/verified",
            ],
            project_rows,
        ),
        "",
        "## Trace Lengths",
        "",
        f"- ShareGPT messages mean/median/max: {traces['sharegpt_messages']['mean']} / {traces['sharegpt_messages']['median']} / {traces['sharegpt_messages']['max']}",
        f"- ShareGPT chars mean/median/max: {traces['sharegpt_chars']['mean']} / {traces['sharegpt_chars']['median']} / {traces['sharegpt_chars']['max']}",
        f"- Mini messages mean/median/max: {traces['mini_messages']['mean']} / {traces['mini_messages']['median']} / {traces['mini_messages']['max']}",
        f"- Assistant responses mean/median/max: {traces['assistant_responses']['mean']} / {traces['assistant_responses']['median']} / {traces['assistant_responses']['max']}",
        f"- Bash calls mean/median/max: {traces['bash_calls']['mean']} / {traces['bash_calls']['median']} / {traces['bash_calls']['max']}",
        "",
        "## Tool Calls",
        "",
        f"- Tool call rounds min/max/mean/median: {stat_text(traces['tool_call_rounds'])}",
        f"- Tool calls total: {tool_calls['tool_calls_total']}",
        f"- Tool calls per trial min/max/mean/median: {stat_text(tool_calls['tool_calls_per_trial'])}",
        f"- Tool argument chars min/max/mean/median: {stat_text(tool_calls['tool_argument_chars'])}",
        f"- Tool argument tokens min/max/mean/median: {stat_text(tool_calls['tool_argument_tokens'])}",
        f"- Tool observation chars min/max/mean/median: {stat_text(tool_calls['tool_observation_chars'])}",
        f"- Tool observation tokens min/max/mean/median: {stat_text(tool_calls['tool_observation_tokens'])}",
        f"- Tool error count: {tool_calls['tool_error_count']}",
        f"- Tool validation error count: {tool_calls['tool_validation_error_count']}",
        "",
        "### Tool Counts",
        "",
        "| Tool | Count | Arg tokens min/max/mean/median | Observation tokens min/max/mean/median |",
        "| --- | ---: | ---: | ---: |",
        *[
            "| {name} | {count} | {arg_tokens} | {obs_tokens} |".format(
                name=name,
                count=stats["count"],
                arg_tokens=stat_text(stats["argument_tokens"]),
                obs_tokens=stat_text(stats["observation_tokens"]),
            )
            for name, stats in tool_calls["tool_name_stats"].items()
        ],
        "",
        "## Tokens",
        "",
        f"- Input tokens mean/median/max: {tokens['input']['mean']} / {tokens['input']['median']} / {tokens['input']['max']}",
        f"- Cached tokens mean/median/max: {tokens['cached']['mean']} / {tokens['cached']['median']} / {tokens['cached']['max']}",
        f"- Output tokens mean/median/max: {tokens['output']['mean']} / {tokens['output']['median']} / {tokens['output']['max']}",
        f"- Total tokens mean/median/max: {tokens['total']['mean']} / {tokens['total']['median']} / {tokens['total']['max']}",
        "",
        "## Cost",
        "",
        f"- Agent result total cost: {costs['agent_result_cost_usd_total']:.6f}",
        f"- Agent result cost mean/median/max: {costs['agent_result_cost_usd']['mean']} / {costs['agent_result_cost_usd']['median']} / {costs['agent_result_cost_usd']['max']}",
        f"- Mini trajectory total cost: {costs['mini_trajectory_cost_usd_total']:.6f}",
        "",
        "## Timing",
        "",
        f"- Trial seconds mean/median/max: {timing['trial_duration_sec']['mean']} / {timing['trial_duration_sec']['median']} / {timing['trial_duration_sec']['max']}",
        "",
        "## Interpretation",
        "",
        "- The headline all-trial resolved rate is dominated by infrastructure/configuration failures, not only model quality.",
        "- The largest class is `artifact_write_argument_list_too_long`, which happens while writing large mini trajectories through `/bin/sh`; those runs often reached submission before Harbor marked the trial as an exception.",
        "- `unsupported_temperature_parameter` points to the GPT-5.5/Macaron endpoint rejecting the configured `temperature` parameter.",
        "- `auth_token_revoked` indicates a credential/session issue late in the run.",
    ]
    path.write_text("\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a mini-swe-agent Harbor job.")
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "analysis")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = analyze(args.job_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.job_dir.name
    json_path = args.out_dir / f"{stem}_mini_analysis.json"
    md_path = args.out_dir / f"{stem}_mini_analysis.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    write_markdown(report, md_path)
    perf = report["performance"]
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(
        "performance: "
        f"trials={perf['total_trials']} "
        f"verified={perf['verified_trials']} "
        f"errors={perf['errors']} "
        f"resolved={perf['resolved']} "
        f"resolved_all={perf['resolved_rate_all']:.4f} "
        f"resolved_verified={perf['resolved_rate_verified']:.4f}"
    )


if __name__ == "__main__":
    main()
