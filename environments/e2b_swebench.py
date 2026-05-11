import os
import re
from pathlib import Path
from typing import Any

from dirhash import dirhash
from dockerfile_parse import DockerfileParser
from e2b import AsyncSandbox, AsyncTemplate, Template
from e2b.api import handle_api_exception
from e2b.api.client.api.templates import get_templates
from e2b.api.client.models import Error
from e2b.api.client_async import get_api_client
from e2b.connection_config import ConnectionConfig
from e2b.exceptions import SandboxException, TemplateException
from tenacity import retry, stop_after_attempt, wait_exponential

from harbor.environments.e2b import E2BEnvironment


def _safe_template_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-_.")
    return segment or "swebench-task"


def _strip_dockerfile_comments(content: str) -> str:
    lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


PI_TEMPLATE_INSTALL_DOCKERFILE = r"""
RUN if command -v apt-get >/dev/null 2>&1; then apt-get update && apt-get install -y curl ca-certificates git jq ripgrep; elif command -v apk >/dev/null 2>&1; then apk add --no-cache curl ca-certificates git jq ripgrep nodejs npm bash; elif command -v yum >/dev/null 2>&1; then yum install -y curl ca-certificates git jq ripgrep; fi
RUN set -e; if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash; export NVM_DIR="/root/.nvm"; . "$NVM_DIR/nvm.sh"; nvm install 22; nvm alias default 22; fi; if [ -s /root/.nvm/nvm.sh ]; then . /root/.nvm/nvm.sh; fi; npm install -g @earendil-works/pi-coding-agent@latest; pi --version
RUN set -e; for bin in node npm npx pi; do BIN_PATH="$(command -v "$bin" 2>/dev/null || true)"; if [ -n "$BIN_PATH" ] && [ "$BIN_PATH" != "/usr/local/bin/$bin" ]; then ln -sf "$BIN_PATH" "/usr/local/bin/$bin"; fi; done
"""


class E2BSwebenchEnvironment(E2BEnvironment):
    """E2B adapter that uses the caller's team namespace for SWE-Bench templates."""

    def __init__(
        self,
        *args: Any,
        template_namespace: str | None = None,
        pi_template_suffix: str | None = None,
        strip_dockerfile_comments: bool = True,
        sandbox_timeout_sec: int | None = None,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)

        namespace = template_namespace or os.getenv("E2B_TEMPLATE_NAMESPACE")
        namespace = _safe_template_segment(namespace or "anchen1011")
        digest = dirhash(self.environment_dir, "sha256")[:8]

        self._template_namespace = namespace
        self._environment_hash = digest
        self._pi_template_suffix = (
            pi_template_suffix
            if pi_template_suffix is not None
            else os.getenv("E2B_PI_TEMPLATE_SUFFIX", "pi_c6d7003a")
        ).strip("_")
        self._template_name = self._build_template_name()
        self._strip_dockerfile_comments = strip_dockerfile_comments
        self._sandbox_timeout_sec = self._resolve_sandbox_timeout_sec(
            sandbox_timeout_sec
        )

    def _legacy_template_base(self) -> str:
        return self.environment_name.replace("/", "__").replace(".", "-")

    def _safe_template_base(self) -> str:
        return _safe_template_segment(self.environment_name)

    def _qualified_template_name(self, base: str) -> str:
        return f"{self._template_namespace}/{base}"

    def _build_template_name(self) -> str:
        return self._qualified_template_name(
            f"{self._safe_template_base()}__{self._environment_hash}"
        )

    def _pi_template_name(self) -> str | None:
        if not self._pi_template_suffix:
            return None
        legacy_name = f"{self._legacy_template_base()}__{self._environment_hash}"
        return self._qualified_template_name(
            f"{legacy_name}__{self._pi_template_suffix}"
        )

    def _candidate_template_names(self) -> list[str]:
        legacy_name = f"{self._legacy_template_base()}__{self._environment_hash}"
        candidates: list[str] = []
        pi_template_name = self._pi_template_name()
        if pi_template_name:
            candidates.append(pi_template_name)
        candidates.extend(
            [
                self._qualified_template_name(legacy_name),
                self._build_template_name(),
            ]
        )
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _resolve_sandbox_timeout_sec(value: int | None) -> int:
        raw_value = value if value is not None else os.getenv("E2B_SANDBOX_TIMEOUT_SEC")
        try:
            timeout = int(raw_value) if raw_value is not None else 3600
        except (TypeError, ValueError):
            timeout = 3600
        return max(60, min(timeout, 3600))

    def _dockerfile_content_or_path(self) -> str:
        content = self._environment_definition_path.read_text(encoding="utf-8")
        if self._strip_dockerfile_comments:
            content = _strip_dockerfile_comments(content)
        if self._template_name == self._pi_template_name():
            content = content.rstrip() + "\n\n" + PI_TEMPLATE_INSTALL_DOCKERFILE
        return content

    def _is_pi_template(self) -> bool:
        return self._template_name == self._pi_template_name()

    def _fallback_template_name(self) -> str:
        legacy_name = f"{self._legacy_template_base()}__{self._environment_hash}"
        return self._qualified_template_name(legacy_name)

    async def _template_exists_exact(self, template_name: str) -> bool:
        config = ConnectionConfig()
        api_client = get_api_client(
            config,
            require_api_key=True,
            require_access_token=False,
        )
        response = await get_templates.asyncio_detailed(client=api_client)
        if response.status_code >= 300:
            raise handle_api_exception(response, TemplateException)
        if response.parsed is None or isinstance(response.parsed, Error):
            return False
        for template in response.parsed:
            if template_name in template.names:
                return True
            if any(
                self._qualified_template_name(alias) == template_name
                for alias in template.aliases
                if "/" not in alias
            ):
                return True
        return False

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _create_template(self):
        if self.task_env_config.docker_image:
            template = Template().from_image(
                image=self.task_env_config.docker_image,
            )
        else:
            template = Template(
                file_context_path=str(Path(self.environment_dir).resolve())
            ).from_dockerfile(
                dockerfile_content_or_path=self._dockerfile_content_or_path(),
            )

        await AsyncTemplate.build(
            template=template,
            name=self._template_name,
            cpu_count=self.task_env_config.cpus,
            memory_mb=self.task_env_config.memory_mb,
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _create_sandbox(self):
        metadata = {
            "environment_name": self.environment_name,
            "session_id": self.session_id,
        }

        try:
            self._sandbox = await AsyncSandbox.create(
                template=self._template_name,
                metadata=metadata,
                timeout=self._sandbox_timeout_sec,
                allow_internet_access=self.task_env_config.allow_internet,
            )
        except SandboxException as exc:
            if not self._is_pi_template() or "tag 'default' does not exist" not in str(exc):
                raise

            fallback_template = self._fallback_template_name()
            self.logger.warning(
                "Falling back from unusable Pi template %s to %s: %s",
                self._template_name,
                fallback_template,
                exc,
            )
            self._template_name = fallback_template
            if not await self._template_exists_exact(fallback_template):
                await self._create_template()
            self._sandbox = await AsyncSandbox.create(
                template=self._template_name,
                metadata=metadata,
                timeout=self._sandbox_timeout_sec,
                allow_internet_access=self.task_env_config.allow_internet,
            )

    async def _does_template_exist(self) -> bool:
        config = ConnectionConfig()
        api_client = get_api_client(
            config,
            require_api_key=True,
            require_access_token=False,
        )
        response = await get_templates.asyncio_detailed(client=api_client)
        if response.status_code >= 300:
            raise handle_api_exception(response, TemplateException)
        if response.parsed is None or isinstance(response.parsed, Error):
            return False
        available_names: set[str] = set()
        for template in response.parsed:
            available_names.update(template.names)
            available_names.update(
                self._qualified_template_name(alias)
                for alias in template.aliases
                if "/" not in alias
            )
        pi_template_name = self._pi_template_name()
        if pi_template_name:
            if pi_template_name in available_names:
                self._template_name = pi_template_name
                return True
            self._template_name = pi_template_name
            return False

        for candidate in self._candidate_template_names():
            if candidate in available_names:
                self._template_name = candidate
                return True
        self._template_name = self._build_template_name()
        return False

    def _workdir_from_dockerfile(self) -> str | None:
        return next(
            (
                instruction["value"]
                for instruction in reversed(
                    DockerfileParser(
                        path=str(self._environment_definition_path)
                    ).structure
                )
                if instruction.get("instruction") == "WORKDIR"
            ),
            None,
        )
