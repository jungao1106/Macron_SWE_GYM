import json
import os
import shlex
import asyncio
import base64
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

from agents.pi_novita_agent import _compact, _int_value


MINI_SYSTEM_PROMPT = """You are mini-SWE-agent, a software engineering agent running inside a Harbor SWE-Bench task sandbox.

Goal:
- Modify the repository in the current working directory so the benchmark issue is fixed.
- Prefer small, targeted source changes. Do not change tests unless the task explicitly requires it.
- Inspect the repository before editing. Run relevant tests when practical.
- Leave the final state in the working tree; Harbor will run the verifier after you exit.

Operational constraints:
- Use the bash tool for all inspection, edits, and tests.
- Do not ask the user for clarification during benchmark execution.
- Do not exfiltrate secrets or print environment variables containing API keys.
- When finished, run exactly: echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
"""

MINI_TEXTBASED_SYSTEM_PROMPT = MINI_SYSTEM_PROMPT + """
Bash action format:
- Every assistant response must contain exactly one bash command in this fenced format:
```mswea_bash_command
command
```
- Do not call tools through JSON/function-call syntax in this mode.
"""


MINI_INSTANCE_TEMPLATE = """Please solve this issue: {{task}}

You can execute bash commands and edit files to implement the necessary changes.

## Recommended Workflow

1. Analyze the codebase by finding and reading relevant files.
2. Create or run a minimal reproduction when practical.
3. Edit the source code to resolve the issue.
4. Verify your fix with focused tests when practical.
5. Finish by issuing exactly this command and no other command:
   `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`

## Rules

- Every response must include at least one bash tool call.
- Directory or environment variable changes are not persistent between actions.
- Keep changes focused on the task.

<system_information>
{{system}} {{release}} {{version}} {{machine}}
</system_information>
"""


MINI_OBSERVATION_TEMPLATE = """{% if output.exception_info -%}
<exception>{{output.exception_info}}</exception>
{% endif -%}
<returncode>{{output.returncode}}</returncode>
<output>
{{ output.output -}}
</output>"""


MINI_FORMAT_ERROR_TEMPLATE = """Tool call error:

<error>
{{error}}
</error>

Every response must use the bash tool at least once.
If you have completed the assignment, run exactly:
`echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`
"""


class MiniHarborEnvironment:
    """mini-SWE-agent environment facade that executes actions through Harbor/E2B."""

    def __init__(self, environment: BaseEnvironment, env: dict[str, str], cwd: str = "", timeout: int = 60):
        self.environment = environment
        self.env = env
        self.cwd = cwd
        self.timeout = timeout
        self._loop: asyncio.AbstractEventLoop | None = None

    def execute(self, action: dict[str, Any], cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        from minisweagent.exceptions import Submitted

        if self._loop is None:
            raise RuntimeError("MiniHarborEnvironment loop has not been attached.")
        command = action.get("command", "")
        future = asyncio.run_coroutine_threadsafe(
            self.environment.exec(
                command=command,
                cwd=cwd or self.cwd or None,
                env=self.env,
                timeout_sec=timeout or self.timeout,
            ),
            self._loop,
        )
        result = future.result()
        output = {
            "output": (result.stdout or "") + (result.stderr or ""),
            "returncode": result.return_code,
            "exception_info": "",
        }
        lines = output["output"].lstrip().splitlines(keepends=True)
        if lines and lines[0].strip() == "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" and output["returncode"] == 0:
            submission = "".join(lines[1:])
            raise Submitted(
                {
                    "role": "exit",
                    "content": submission,
                    "extra": {"exit_status": "Submitted", "submission": submission},
                }
            )
        return output

    def get_template_vars(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "system": "Linux",
            "release": "",
            "version": "",
            "machine": "",
            "cwd": self.cwd,
            **os.environ,
            **kwargs,
        }

    def serialize(self) -> dict[str, Any]:
        return {
            "info": {
                "config": {
                    "environment": {"cwd": self.cwd},
                    "environment_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                }
            }
        }


def _safe_shell_json(value: dict[str, Any]) -> str:
    return shlex.quote(json.dumps(value, ensure_ascii=False, indent=2))


def _base64_chunks(text: str, chunk_size: int = 60_000) -> list[str]:
    """Return shell-safe base64 chunks with decoder-friendly boundaries."""
    chunk_size -= chunk_size % 4
    encoded = base64.b64encode(text.encode()).decode()
    return [encoded[index : index + chunk_size] for index in range(0, len(encoded), chunk_size)]


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("output")
                if text is not None:
                    parts.append(str(text))
        return "".join(parts)
    return str(content) if content is not None else ""


class MiniSweAgent(BaseInstalledAgent):
    """Harbor installed-agent adapter for mini-SWE-agent on E2B tasks."""

    SUPPORTS_ATIF = True

    _TRAJECTORY_FILENAME = "trajectory.json"
    _MINI_TRAJECTORY_FILENAME = "mini-trajectory.json"
    _SHAREGPT_FILENAME = "sharegpt.json"
    _METADATA_FILENAME = "mini-metadata.json"
    _INSTRUCTION_FILENAME = "problem_statement.md"
    _CONFIG_FILENAME = "mini-config.yaml"
    _STDOUT_FILENAME = "mini-stdout.txt"
    _STDERR_FILENAME = "mini-stderr.txt"

    def __init__(
        self,
        logs_dir: Path,
        provider_name: str = "macaron",
        api_key_env: str = "MACARON_API_KEY",
        base_url_env: str = "MACARON_BASE_URL",
        model_env: str = "MACARON_MODEL",
        model_class: str = "litellm_response",
        cost_tracking: str = "ignore_errors",
        step_limit: int = 250,
        cost_limit: float = 0.0,
        command_timeout_sec: int = 60,
        request_timeout_sec: float | None = None,
        temperature: float = 0.0,
        model_kwargs: dict[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(logs_dir=logs_dir, *args, **kwargs)
        self.provider_name = provider_name
        self.api_key_env = api_key_env
        self.base_url_env = base_url_env
        self.model_env = model_env
        self.model_class = model_class
        self.cost_tracking = cost_tracking
        self.step_limit = step_limit
        self.cost_limit = cost_limit
        self.command_timeout_sec = command_timeout_sec
        self.request_timeout_sec = request_timeout_sec
        self.temperature = temperature
        self.model_kwargs = model_kwargs or {}

    @staticmethod
    def name() -> str:
        return "mini-swe-agent"

    def get_version_command(self) -> str | None:
        return (
            "python - <<'PY'\n"
            "import minisweagent\n"
            "print(minisweagent.__version__)\n"
            "PY"
        )

    def parse_version(self, stdout: str) -> str:
        for line in stdout.strip().splitlines():
            line = line.strip()
            if line and "mini-swe-agent" not in line and "Loading global config" not in line:
                return line
        return stdout.strip()

    async def install(self, environment: BaseEnvironment) -> None:
        import minisweagent

        self._version = minisweagent.__version__

    def _required_env(self) -> dict[str, str]:
        required = [self.api_key_env, self.base_url_env, self.model_env]
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ValueError(
                "Missing required environment variables for MiniSweAgent: "
                + ", ".join(missing)
            )
        return {name: os.environ[name] for name in required}

    def _config(self, env: dict[str, str]) -> dict[str, Any]:
        model_kwargs: dict[str, Any] = {
            "drop_params": True,
            "custom_llm_provider": "openai",
            "api_base": env[self.base_url_env],
        }
        model_kwargs.update(self.model_kwargs)
        if self.request_timeout_sec and "timeout" not in model_kwargs:
            model_kwargs["timeout"] = self.request_timeout_sec
        if self.temperature is not None and "temperature" not in model_kwargs:
            model_kwargs["temperature"] = self.temperature
        if self.provider_name == "macaron" and "instructions" not in model_kwargs:
            model_kwargs["instructions"] = (
                "You are mini-SWE-agent. Use the bash tool to solve the user's "
                "software engineering task."
            )
        return {
            "agent": {
                "system_template": (
                    MINI_TEXTBASED_SYSTEM_PROMPT
                    if self.model_class == "litellm_textbased"
                    else MINI_SYSTEM_PROMPT
                ),
                "instance_template": MINI_INSTANCE_TEMPLATE,
                "step_limit": self.step_limit,
                "cost_limit": self.cost_limit,
                "output_path": str(EnvironmentPaths.agent_dir / self._MINI_TRAJECTORY_FILENAME),
            },
            "environment": {
                "cwd": "",
                "timeout": self.command_timeout_sec,
            },
            "model": {
                "model_class": self.model_class,
                "model_name": env[self.model_env],
                "cost_tracking": self.cost_tracking,
                "model_kwargs": model_kwargs,
                "observation_template": MINI_OBSERVATION_TEMPLATE,
                "format_error_template": MINI_FORMAT_ERROR_TEMPLATE,
            },
        }

    async def _write_agent_file(
        self,
        environment: BaseEnvironment,
        path: PurePosixPath,
        text: str,
        env: dict[str, str],
    ) -> None:
        quoted_path = shlex.quote(str(path))
        await self.exec_as_agent(
            environment,
            command=f"mkdir -p {shlex.quote(str(path.parent))} && : > {quoted_path}",
            env=env,
        )
        for chunk in _base64_chunks(text):
            await self.exec_as_agent(
                environment,
                command=f"printf '%s' {shlex.quote(chunk)} | base64 -d >> {quoted_path}",
                env=env,
            )

    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        from minisweagent.agents.default import DefaultAgent
        from minisweagent.models import get_model

        env = self._required_env()
        config = self._config(env)
        metadata = {
            "agent": self.name(),
            "mini_version": self._version,
            "provider": self.provider_name,
            "provider_model": env[self.model_env],
            "provider_base_url": env[self.base_url_env],
            "api_key_env": self.api_key_env,
            "base_url_env": self.base_url_env,
            "model_env": self.model_env,
            "model_class": self.model_class,
            "system_prompt": config["agent"]["system_template"],
        }

        instruction_path = PurePosixPath(EnvironmentPaths.agent_dir / self._INSTRUCTION_FILENAME)
        config_path = PurePosixPath(EnvironmentPaths.agent_dir / self._CONFIG_FILENAME)
        metadata_path = PurePosixPath(EnvironmentPaths.agent_dir / self._METADATA_FILENAME)
        stdout_path = PurePosixPath(EnvironmentPaths.agent_dir / self._STDOUT_FILENAME)
        stderr_path = PurePosixPath(EnvironmentPaths.agent_dir / self._STDERR_FILENAME)

        heredoc = "HARBOR_MINI_PROMPT_EOF"
        setup_command = (
            "set -euo pipefail\n"
            "mkdir -p /logs/agent\n"
            f"cat > {shlex.quote(str(instruction_path))} <<'{heredoc}'\n"
            f"{instruction}\n"
            f"{heredoc}\n"
            f"printf '%s\\n' {_safe_shell_json(config)} > {shlex.quote(str(config_path))}\n"
            f"printf '%s\\n' {_safe_shell_json(metadata)} > {shlex.quote(str(metadata_path))}\n"
        )
        await self.exec_as_agent(environment, command=setup_command, env=env)

        os.environ["OPENAI_API_KEY"] = env[self.api_key_env]
        os.environ["MSWEA_CONFIGURED"] = "true"
        os.environ["MSWEA_SILENT_STARTUP"] = "1"
        os.environ["MSWEA_COST_TRACKING"] = "ignore_errors"

        loop = asyncio.get_running_loop()
        mini_env = MiniHarborEnvironment(
            environment,
            env=env,
            timeout=self.command_timeout_sec,
        )
        mini_env._loop = loop
        model = get_model(config=config.get("model", {}))
        agent = DefaultAgent(model, mini_env, **config.get("agent", {}))
        info = await asyncio.to_thread(agent.run, instruction)

        mini_traj = agent.save(
            self.logs_dir / self._MINI_TRAJECTORY_FILENAME,
            {"info": {"exit_status": info.get("exit_status"), "submission": info.get("submission")}},
        )
        (self.logs_dir / self._CONFIG_FILENAME).write_text(
            json.dumps(config, ensure_ascii=False, indent=2)
        )
        (self.logs_dir / self._METADATA_FILENAME).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2)
        )
        (self.logs_dir / self._STDOUT_FILENAME).write_text(
            f"exit_status={info.get('exit_status')}\n"
        )
        (self.logs_dir / self._STDERR_FILENAME).write_text("")

        await self._write_agent_file(
            environment,
            PurePosixPath(EnvironmentPaths.agent_dir / self._MINI_TRAJECTORY_FILENAME),
            json.dumps(mini_traj, ensure_ascii=False, indent=2) + "\n",
            env,
        )

    def _mini_trajectory(self) -> dict[str, Any]:
        path = self.logs_dir / self._MINI_TRAJECTORY_FILENAME
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(errors="replace"))
        except json.JSONDecodeError:
            return {}

    def _metadata(self) -> dict[str, Any]:
        path = self.logs_dir / self._METADATA_FILENAME
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(errors="replace"))
        except json.JSONDecodeError:
            return {}

    def _instruction_text(self) -> str:
        path = self.logs_dir / self._INSTRUCTION_FILENAME
        return path.read_text(errors="replace") if path.exists() else ""

    def _convert_to_trajectory(self, mini_traj: dict[str, Any], metadata: dict[str, Any]) -> Trajectory | None:
        messages = mini_traj.get("messages")
        if not isinstance(messages, list):
            return None

        model_name = str(
            mini_traj.get("info", {})
            .get("config", {})
            .get("model", {})
            .get("model_name")
            or metadata.get("provider_model")
            or self.model_name
            or ""
        )
        steps: list[Step] = []
        step_id = 1
        pending_tool_steps: list[tuple[str, Step]] = []

        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            message_type = message.get("type")
            extra = message.get("extra") if isinstance(message.get("extra"), dict) else {}

            if message_type == "function_call_output":
                output = str(message.get("output") or extra.get("raw_output") or "")
                call_id, step = (
                    pending_tool_steps.pop(0)
                    if pending_tool_steps
                    else (str(message.get("call_id") or f"mini-tool-{step_id}"), None)
                )
                observation_result = ObservationResult(
                    source_call_id=call_id,
                    content=output,
                )
                if step is not None:
                    if step.observation is None:
                        step.observation = Observation(results=[observation_result])
                    else:
                        step.observation.results.append(observation_result)
                continue

            if role not in ("system", "user", "assistant", "exit"):
                continue
            text = _message_content_text(message.get("content") or message.get("output"))
            source = {"assistant": "agent", "exit": "agent"}.get(str(role), str(role))
            actions = extra.get("actions") if isinstance(extra.get("actions"), list) else []
            tool_calls = []
            for index, action in enumerate(actions):
                if not isinstance(action, dict):
                    continue
                call_id = str(action.get("tool_call_id") or f"mini-tool-{step_id}-{index}")
                tool_calls.append(
                    ToolCall(
                        tool_call_id=call_id,
                        function_name="bash",
                        arguments={"command": action.get("command", "")},
                    )
                )
            step = Step(
                step_id=step_id,
                source=source,
                message=text,
                model_name=(model_name or None) if source == "agent" else None,
                tool_calls=tool_calls or None,
            )
            steps.append(step)
            for tool_call in tool_calls:
                pending_tool_steps.append((tool_call.tool_call_id, step))
            step_id += 1

        if not steps:
            return None

        info = mini_traj.get("info") if isinstance(mini_traj.get("info"), dict) else {}
        model_stats = info.get("model_stats") if isinstance(info.get("model_stats"), dict) else {}
        final_metrics = FinalMetrics(
            total_prompt_tokens=None,
            total_completion_tokens=None,
            total_cached_tokens=None,
            total_cost_usd=model_stats.get("instance_cost") or None,
            total_steps=len(steps),
            extra={
                "api_calls": _int_value(model_stats.get("api_calls")),
                "exit_status": info.get("exit_status"),
                "tool_call_rounds": sum(1 for step in steps if step.tool_calls),
            },
        )

        return Trajectory(
            schema_version="ATIF-v1.6",
            session_id="mini-swe-agent-session",
            agent=Agent(
                name=self.name(),
                version=str(info.get("mini_version") or metadata.get("mini_version") or self._version or "unknown"),
                model_name=model_name or None,
                extra={
                    "provider": metadata.get("provider"),
                    "provider_base_url": metadata.get("provider_base_url"),
                    "provider_model": metadata.get("provider_model"),
                    "model_class": metadata.get("model_class"),
                    "system_prompt": metadata.get("system_prompt"),
                },
            ),
            steps=steps,
            final_metrics=final_metrics,
        )

    def _convert_to_sharegpt(
        self,
        mini_traj: dict[str, Any],
        metadata: dict[str, Any],
        trajectory: Trajectory | None,
    ) -> dict[str, Any]:
        conversations: list[dict[str, str]] = []
        for message in mini_traj.get("messages", []):
            if not isinstance(message, dict):
                continue
            role = message.get("role") or message.get("type")
            text = _message_content_text(message.get("content") or message.get("output"))
            if not text:
                continue
            if role == "assistant":
                conversations.append({"from": "gpt", "value": text})
            elif role in ("system", "user"):
                conversations.append({"from": "human" if role == "user" else "system", "value": text})
            elif role == "tool" or message.get("type") == "function_call_output":
                conversations.append({"from": "tool", "value": text})
            elif role == "exit":
                conversations.append({"from": "gpt", "value": text})

        trace_chars = sum(len(item["value"]) for item in conversations)
        return {
            "id": trajectory.session_id if trajectory else "mini-swe-agent-session",
            "source": "harbor-swebench-verified",
            "model": metadata.get("provider_model") or self.model_name,
            "conversations": conversations,
            "metadata": {
                "agent": self.name(),
                "provider": metadata.get("provider"),
                "provider_model": metadata.get("provider_model"),
                "trace_messages": len(conversations),
                "trace_chars": trace_chars,
                "tool_call_rounds": sum(
                    1
                    for step in (trajectory.steps if trajectory else [])
                    if step.tool_calls
                ),
            },
        }

    def populate_context_post_run(self, context: AgentContext) -> None:
        mini_traj = self._mini_trajectory()
        metadata = self._metadata()
        trajectory = self._convert_to_trajectory(mini_traj, metadata)

        if trajectory is not None:
            trajectory_path = self.logs_dir / self._TRAJECTORY_FILENAME
            trajectory_path.write_text(format_trajectory_json(trajectory.to_json_dict()))
            if trajectory.final_metrics:
                context.cost_usd = trajectory.final_metrics.total_cost_usd

        sharegpt = self._convert_to_sharegpt(mini_traj, metadata, trajectory)
        (self.logs_dir / self._SHAREGPT_FILENAME).write_text(
            json.dumps(sharegpt, ensure_ascii=False, indent=2)
        )

        context.metadata = {
            "sharegpt_path": str(self.logs_dir / self._SHAREGPT_FILENAME),
            "trajectory_path": str(self.logs_dir / self._TRAJECTORY_FILENAME),
            "mini_trajectory_path": str(self.logs_dir / self._MINI_TRAJECTORY_FILENAME),
            "mini_system_prompt": metadata.get("system_prompt") or MINI_SYSTEM_PROMPT,
            "mini_tool_call_rounds": sharegpt["metadata"]["tool_call_rounds"],
            "sharegpt_trace_messages": sharegpt["metadata"]["trace_messages"],
            "sharegpt_trace_chars": sharegpt["metadata"]["trace_chars"],
        }
