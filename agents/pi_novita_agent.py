import json
import os
import shlex
from pathlib import Path, PurePosixPath
from typing import Any

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trajectories import (
    Agent,
    FinalMetrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)
from harbor.models.trial.paths import EnvironmentPaths
from harbor.utils.trajectory_utils import format_trajectory_json


PI_SYSTEM_PROMPT = """You are Pi, a terminal-based software engineering agent running inside a Harbor SWE-Bench task sandbox.

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
"""


def _json_default(value: Any) -> str:
    return str(value)


def _compact(value: Any, limit: int = 6000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=_json_default)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [truncated]"


def _numeric_value(value: Any) -> int | float:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0
    return 0


def _int_value(*values: Any) -> int:
    for value in values:
        numeric = _numeric_value(value)
        if numeric:
            return int(numeric)
    return 0


def _cost_value(value: Any) -> float:
    if isinstance(value, dict):
        return float(_numeric_value(value.get("total")))
    return float(_numeric_value(value))


def _message_text(message: dict[str, Any] | None) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text is not None:
                    parts.append(str(text))
        return "".join(parts)
    text = message.get("text")
    return str(text) if text is not None else ""


def _safe_shell_json(value: dict[str, Any]) -> str:
    return shlex.quote(json.dumps(value, ensure_ascii=False, indent=2))


class PiNovitaAgent(BaseInstalledAgent):
    """Harbor installed-agent adapter that runs Pi against OpenAI-compatible models."""

    SUPPORTS_ATIF = True

    _JSONL_FILENAME = "pi-events.jsonl"
    _STDERR_FILENAME = "pi-stderr.txt"
    _SHAREGPT_FILENAME = "sharegpt.json"
    _TRAJECTORY_FILENAME = "trajectory.json"
    _METADATA_FILENAME = "pi-metadata.json"
    _MODELS_FILENAME = "models.json"
    _SYSTEM_PROMPT_FILENAME = "pi-system-prompt.md"
    _INSTRUCTION_FILENAME = "problem_statement.md"

    def __init__(
        self,
        logs_dir: Path,
        provider_name: str = "novita",
        api_key_env: str = "NOVITA_API_KEY",
        base_url_env: str = "NOVITA_BASE_URL",
        model_env: str = "NOVITA_MODEL",
        model_context_window: int = 128000,
        model_max_tokens: int = 32000,
        thinking: str = "off",
        tools: str = "read,write,edit,bash,grep,find,ls",
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(logs_dir=logs_dir, *args, **kwargs)
        self.provider_name = provider_name
        self.api_key_env = api_key_env
        self.base_url_env = base_url_env
        self.model_env = model_env
        self.model_context_window = model_context_window
        self.model_max_tokens = model_max_tokens
        self.thinking = thinking
        self.tools = tools

    @staticmethod
    def name() -> str:
        return "pi-novita"

    @property
    def _trajectory_path(self) -> PurePosixPath:
        return PurePosixPath(EnvironmentPaths.agent_dir / self._TRAJECTORY_FILENAME)

    def get_version_command(self) -> str | None:
        return "if [ -s ~/.nvm/nvm.sh ]; then . ~/.nvm/nvm.sh; fi; pi --version"

    def parse_version(self, stdout: str) -> str:
        for line in stdout.strip().splitlines():
            if line.strip():
                return line.strip()
        return stdout.strip()

    async def install(self, environment: BaseEnvironment) -> None:
        pi_check = await environment.exec(
            command=(
                "if [ -s ~/.nvm/nvm.sh ]; then . ~/.nvm/nvm.sh; fi; "
                "command -v pi >/dev/null 2>&1 && pi --version"
            )
        )
        if pi_check.return_code == 0:
            parsed_version = self.parse_version(pi_check.stdout)
            if parsed_version:
                self._version = parsed_version
            await self.exec_as_root(
                environment,
                command=(
                    "set -e; "
                    "for bin in node npm npx pi; do "
                    '  BIN_PATH="$(command -v "$bin" 2>/dev/null || true)"; '
                    '  if [ -n "$BIN_PATH" ] && [ "$BIN_PATH" != "/usr/local/bin/$bin" ]; then '
                    '    ln -sf "$BIN_PATH" "/usr/local/bin/$bin"; '
                    "  fi; "
                    "done"
                ),
            )
            return

        await self.exec_as_root(
            environment,
            command=(
                "if command -v apt-get >/dev/null 2>&1; then "
                "apt-get update && apt-get install -y curl ca-certificates git jq ripgrep; "
                "elif command -v apk >/dev/null 2>&1; then "
                "apk add --no-cache curl ca-certificates git jq ripgrep nodejs npm bash; "
                "elif command -v yum >/dev/null 2>&1; then "
                "yum install -y curl ca-certificates git jq ripgrep; "
                "fi"
            ),
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )

        version_spec = f"@{self._version}" if self._version else "@latest"
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                "if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then "
                "  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash; "
                '  export NVM_DIR="$HOME/.nvm"; '
                '  . "$NVM_DIR/nvm.sh"; '
                "  nvm install 22; "
                "  nvm alias default 22; "
                "fi; "
                "if [ -s ~/.nvm/nvm.sh ]; then . ~/.nvm/nvm.sh; fi; "
                f"npm install -g @earendil-works/pi-coding-agent{version_spec}; "
                "pi --version"
            ),
        )

        await self.exec_as_root(
            environment,
            command=(
                "set -e; "
                "for bin in node npm npx pi; do "
                '  BIN_PATH="$(command -v "$bin" 2>/dev/null || true)"; '
                '  if [ -n "$BIN_PATH" ] && [ "$BIN_PATH" != "/usr/local/bin/$bin" ]; then '
                '    ln -sf "$BIN_PATH" "/usr/local/bin/$bin"; '
                "  fi; "
                "done"
            ),
        )

    def _required_env(self) -> dict[str, str]:
        required = [self.api_key_env, self.base_url_env, self.model_env]
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ValueError(
                "Missing required environment variables for PiNovitaAgent: "
                + ", ".join(missing)
            )
        return {name: os.environ[name] for name in required}

    def _models_config(self, env: dict[str, str]) -> dict[str, Any]:
        openai_compat: dict[str, Any] = {
            "supportsStore": False,
            "supportsDeveloperRole": False,
            "supportsReasoningEffort": False,
            "supportsUsageInStreaming": False,
            "maxTokensField": "max_tokens",
            "requiresToolResultName": False,
            "requiresAssistantAfterToolResult": False,
            "requiresThinkingAsText": False,
            "requiresReasoningContentOnAssistantMessages": False,
            "supportsStrictMode": False,
            "supportsLongCacheRetention": False,
        }
        if self.provider_name == "novita":
            openai_compat.update(
                {
                    "requiresThinkingAsText": True,
                    "thinkingFormat": "zai",
                }
            )
        return {
            "providers": {
                self.provider_name: {
                    "baseUrl": env[self.base_url_env],
                    "api": "openai-completions",
                    "apiKey": self.api_key_env,
                    "authHeader": True,
                    "compat": openai_compat,
                    "models": [
                        {
                            "id": env[self.model_env],
                            "name": env[self.model_env],
                            "reasoning": False,
                            "input": ["text"],
                            "contextWindow": self.model_context_window,
                            "maxTokens": self.model_max_tokens,
                            "cost": {
                                "input": 0,
                                "output": 0,
                                "cacheRead": 0,
                                "cacheWrite": 0,
                            },
                            "compat": openai_compat,
                        }
                    ],
                }
            }
        }

    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        env = self._required_env()
        provider_model = env[self.model_env]
        provider_base_url = env[self.base_url_env]
        model = self.model_name or f"{self.provider_name}/{provider_model}"
        models_config = self._models_config(env)
        metadata = {
            "agent": self.name(),
            "pi_version": self._version,
            "provider": self.provider_name,
            "model": model,
            "provider_model": provider_model,
            "provider_base_url": provider_base_url,
            "api_key_env": self.api_key_env,
            "base_url_env": self.base_url_env,
            "model_env": self.model_env,
            "novita_model": provider_model if self.provider_name == "novita" else None,
            "novita_base_url": provider_base_url if self.provider_name == "novita" else None,
            "thinking": self.thinking,
            "tools": self.tools,
            "system_prompt": PI_SYSTEM_PROMPT,
        }

        instruction_path = PurePosixPath(
            EnvironmentPaths.agent_dir / self._INSTRUCTION_FILENAME
        )
        system_prompt_path = PurePosixPath(
            EnvironmentPaths.agent_dir / self._SYSTEM_PROMPT_FILENAME
        )
        models_path = PurePosixPath(EnvironmentPaths.agent_dir / self._MODELS_FILENAME)
        metadata_path = PurePosixPath(
            EnvironmentPaths.agent_dir / self._METADATA_FILENAME
        )
        jsonl_path = PurePosixPath(EnvironmentPaths.agent_dir / self._JSONL_FILENAME)
        stderr_path = PurePosixPath(EnvironmentPaths.agent_dir / self._STDERR_FILENAME)

        heredoc = "HARBOR_PI_PROMPT_EOF"
        system_heredoc = "HARBOR_PI_SYSTEM_EOF"
        command = (
            "set -euo pipefail\n"
            "mkdir -p /logs/agent ~/.pi/agent\n"
            f"cat > {shlex.quote(str(instruction_path))} <<'{heredoc}'\n"
            f"{instruction}\n"
            f"{heredoc}\n"
            f"cat > {shlex.quote(str(system_prompt_path))} <<'{system_heredoc}'\n"
            f"{PI_SYSTEM_PROMPT}\n"
            f"{system_heredoc}\n"
            f"printf '%s\\n' {_safe_shell_json(models_config)} > ~/.pi/agent/models.json\n"
            f"cp ~/.pi/agent/models.json {shlex.quote(str(models_path))}\n"
            f"printf '%s\\n' {_safe_shell_json(metadata)} > {shlex.quote(str(metadata_path))}\n"
            "if [ -s ~/.nvm/nvm.sh ]; then . ~/.nvm/nvm.sh; fi\n"
            "export PI_SKIP_VERSION_CHECK=1\n"
            "export PI_TELEMETRY=0\n"
            "PROMPT=$(cat " + shlex.quote(str(instruction_path)) + ")\n"
            "pi --print --no-session --mode json --no-context-files --no-extensions --no-skills "
            f"--tools {shlex.quote(self.tools)} "
            f"--provider {shlex.quote(self.provider_name)} "
            f"--model {shlex.quote(model)} "
            f"--thinking {shlex.quote(self.thinking)} "
            "--system-prompt "
            f"{shlex.quote(PI_SYSTEM_PROMPT)} "
            '"$PROMPT" '
            f"> {shlex.quote(str(jsonl_path))} "
            f"2> >(tee {shlex.quote(str(stderr_path))} >&2)\n"
        )

        await self.exec_as_agent(environment, command=command, env=env)

    def _jsonl_events(self) -> list[dict[str, Any]]:
        path = self.logs_dir / self._JSONL_FILENAME
        events: list[dict[str, Any]] = []
        if not path.exists():
            return events
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def _metadata(self) -> dict[str, Any]:
        path = self.logs_dir / self._METADATA_FILENAME
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}

    def _instruction_text(self) -> str:
        path = self.logs_dir / self._INSTRUCTION_FILENAME
        if path.exists():
            return path.read_text(errors="replace")
        return ""

    def _extract_usage(self, event: dict[str, Any]) -> dict[str, Any]:
        candidates = [
            event.get("usage"),
            event.get("message", {}).get("usage")
            if isinstance(event.get("message"), dict)
            else None,
            event.get("assistantMessageEvent", {}).get("usage")
            if isinstance(event.get("assistantMessageEvent"), dict)
            else None,
        ]
        usage: dict[str, Any] = {}
        for candidate in candidates:
            if isinstance(candidate, dict):
                usage.update(candidate)
        return usage

    def _convert_to_trajectory(
        self, events: list[dict[str, Any]], metadata: dict[str, Any]
    ) -> Trajectory | None:
        session = next((event for event in events if event.get("type") == "session"), {})
        session_id = str(session.get("id") or "pi-session")
        model_name = str(metadata.get("model") or self.model_name or "")
        version = str(metadata.get("pi_version") or self._version or "unknown")

        steps: list[Step] = []
        step_id = 1
        instruction = self._instruction_text()
        if instruction:
            steps.append(
                Step(
                    step_id=step_id,
                    source="user",
                    message=instruction,
                )
            )
            step_id += 1

        pending_tool_steps: dict[str, Step] = {}
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cached_tokens = 0
        total_cost = 0.0

        for event in events:
            event_type = event.get("type")
            usage = self._extract_usage(event)
            total_prompt_tokens += _int_value(
                usage.get("prompt_tokens")
                or usage.get("input_tokens")
                or usage.get("inputTokens")
                or usage.get("input")
                or 0
            )
            total_completion_tokens += _int_value(
                usage.get("completion_tokens")
                or usage.get("output_tokens")
                or usage.get("outputTokens")
                or usage.get("output")
                or 0
            )
            total_cached_tokens += _int_value(
                usage.get("cached_tokens")
                or usage.get("cache_read_input_tokens")
                or usage.get("cachedInputTokens")
                or usage.get("cacheRead")
                or 0
            )
            total_cost += _cost_value(usage.get("cost_usd") or usage.get("cost"))

            if event_type == "message_end":
                message = event.get("message")
                if not isinstance(message, dict):
                    continue
                role = message.get("role")
                if role not in ("assistant", "user", "system"):
                    continue
                text = _message_text(message)
                if not text:
                    continue
                source = "agent" if role == "assistant" else role
                kwargs: dict[str, Any] = {
                    "step_id": step_id,
                    "source": source,
                    "message": text,
                    "timestamp": event.get("timestamp"),
                }
                if source == "agent":
                    kwargs["model_name"] = model_name or None
                steps.append(Step(**kwargs))
                step_id += 1

            elif event_type == "tool_execution_start":
                call_id = str(event.get("toolCallId") or f"tool-{step_id}")
                tool_name = str(event.get("toolName") or "tool")
                args = event.get("args")
                if not isinstance(args, dict):
                    args = {"value": args}
                step = Step(
                    step_id=step_id,
                    source="agent",
                    message=f"Tool call: {tool_name}",
                    model_name=model_name or None,
                    timestamp=event.get("timestamp"),
                    tool_calls=[
                        ToolCall(
                            tool_call_id=call_id,
                            function_name=tool_name,
                            arguments=args,
                        )
                    ],
                )
                steps.append(step)
                pending_tool_steps[call_id] = step
                step_id += 1

            elif event_type == "tool_execution_end":
                call_id = str(event.get("toolCallId") or "")
                step = pending_tool_steps.get(call_id)
                if step is None:
                    continue
                result = event.get("result")
                is_error = bool(event.get("isError"))
                output = _compact(result)
                if is_error:
                    output = "[error]\n" + output
                observation_result = ObservationResult(
                    source_call_id=call_id,
                    content=output,
                )
                if step.observation is None:
                    step.observation = Observation(results=[observation_result])
                else:
                    step.observation.results.append(observation_result)

        if not steps:
            return None

        final_metrics = FinalMetrics(
            total_prompt_tokens=total_prompt_tokens or None,
            total_completion_tokens=total_completion_tokens or None,
            total_cached_tokens=total_cached_tokens or None,
            total_cost_usd=total_cost or None,
            total_steps=len(steps),
            extra={
                "tool_call_rounds": sum(1 for step in steps if step.tool_calls),
                "json_event_count": len(events),
            },
        )

        return Trajectory(
            schema_version="ATIF-v1.6",
            session_id=session_id,
            agent=Agent(
                name=self.name(),
                version=version,
                model_name=model_name or None,
                extra={
                    "provider": metadata.get("provider"),
                    "provider_base_url": metadata.get("provider_base_url"),
                    "provider_model": metadata.get("provider_model"),
                    "thinking": metadata.get("thinking"),
                    "tools": metadata.get("tools"),
                    "system_prompt": metadata.get("system_prompt"),
                },
            ),
            steps=steps,
            final_metrics=final_metrics,
        )

    def _convert_to_sharegpt(
        self,
        events: list[dict[str, Any]],
        metadata: dict[str, Any],
        trajectory: Trajectory | None,
    ) -> dict[str, Any]:
        conversations: list[dict[str, str]] = []
        system_prompt = str(metadata.get("system_prompt") or PI_SYSTEM_PROMPT)
        conversations.append({"from": "system", "value": system_prompt})

        instruction = self._instruction_text()
        if instruction:
            conversations.append({"from": "human", "value": instruction})

        for event in events:
            event_type = event.get("type")
            if event_type == "message_end":
                message = event.get("message")
                if not isinstance(message, dict):
                    continue
                role = message.get("role")
                text = _message_text(message)
                if not text:
                    continue
                if role == "assistant":
                    conversations.append({"from": "gpt", "value": text})
                elif role == "user":
                    conversations.append({"from": "human", "value": text})
                elif role == "system":
                    conversations.append({"from": "system", "value": text})
            elif event_type == "tool_execution_start":
                tool_name = event.get("toolName") or "tool"
                tool_call_id = event.get("toolCallId") or ""
                args = _compact(event.get("args"))
                conversations.append(
                    {
                        "from": "gpt",
                        "value": f"<tool_call name=\"{tool_name}\" id=\"{tool_call_id}\">\n{args}\n</tool_call>",
                    }
                )
            elif event_type == "tool_execution_end":
                tool_name = event.get("toolName") or "tool"
                tool_call_id = event.get("toolCallId") or ""
                result = _compact(event.get("result"))
                if event.get("isError"):
                    result = "[error]\n" + result
                conversations.append(
                    {
                        "from": "tool",
                        "value": f"<tool_result name=\"{tool_name}\" id=\"{tool_call_id}\">\n{result}\n</tool_result>",
                    }
                )

        trace_chars = sum(len(item["value"]) for item in conversations)
        return {
            "id": trajectory.session_id if trajectory else "pi-session",
            "source": "harbor-swebench-verified",
            "model": metadata.get("model") or self.model_name,
            "conversations": conversations,
            "metadata": {
                "agent": self.name(),
                "provider": metadata.get("provider"),
                "provider_model": metadata.get("provider_model"),
                "trace_messages": len(conversations),
                "trace_chars": trace_chars,
                "tool_call_rounds": sum(
                    1
                    for event in events
                    if event.get("type") == "tool_execution_start"
                ),
                "json_event_count": len(events),
            },
        }

    def populate_context_post_run(self, context: AgentContext) -> None:
        events = self._jsonl_events()
        metadata = self._metadata()
        trajectory = self._convert_to_trajectory(events, metadata)

        if trajectory is not None:
            trajectory_path = self.logs_dir / self._TRAJECTORY_FILENAME
            trajectory_path.write_text(format_trajectory_json(trajectory.to_json_dict()))
            if trajectory.final_metrics:
                context.n_input_tokens = trajectory.final_metrics.total_prompt_tokens
                context.n_cache_tokens = trajectory.final_metrics.total_cached_tokens
                context.n_output_tokens = (
                    trajectory.final_metrics.total_completion_tokens
                )
                context.cost_usd = trajectory.final_metrics.total_cost_usd

        sharegpt = self._convert_to_sharegpt(events, metadata, trajectory)
        (self.logs_dir / self._SHAREGPT_FILENAME).write_text(
            json.dumps(sharegpt, ensure_ascii=False, indent=2)
        )

        context.metadata = {
            "sharegpt_path": str(self.logs_dir / self._SHAREGPT_FILENAME),
            "trajectory_path": str(self.logs_dir / self._TRAJECTORY_FILENAME),
            "pi_system_prompt": metadata.get("system_prompt") or PI_SYSTEM_PROMPT,
            "pi_tool_call_rounds": sharegpt["metadata"]["tool_call_rounds"],
            "pi_json_event_count": len(events),
            "sharegpt_trace_messages": sharegpt["metadata"]["trace_messages"],
            "sharegpt_trace_chars": sharegpt["metadata"]["trace_chars"],
        }
