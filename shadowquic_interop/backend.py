from __future__ import annotations

import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .adapters import SOCKS_PORT, Implementation
from .models import (
    CellResult,
    ProbeResult,
    Protocol,
    Status,
    aggregate_status,
    probe_variants,
)


PROXYPEN_IMAGE = "shadowquic-interop/proxypen:latest"


class BackendError(RuntimeError):
    pass


@dataclass(slots=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


class CommandRunner:
    def run(
        self,
        args: Sequence[str],
        *,
        timeout: int,
        check: bool = True,
    ) -> CommandResult:
        try:
            completed = subprocess.run(
                list(args),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise BackendError(f"command not found: {args[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise BackendError(f"command timed out after {timeout}s: {' '.join(args)}") from exc

        result = CommandResult(
            args=list(args),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if check and result.returncode != 0:
            detail = result.output.strip()[-1000:]
            raise BackendError(
                f"command exited with {result.returncode}: {' '.join(args)}\n{detail}"
            )
        return result


class DockerBackend:
    def __init__(
        self,
        *,
        command_runner: CommandRunner | None = None,
        timeout: int = 30,
        readiness_delay: float = 2.0,
    ) -> None:
        self.commands = command_runner or CommandRunner()
        self.timeout = timeout
        self.readiness_delay = readiness_delay

    def prepare(self, *, build: bool = True) -> None:
        self.commands.run(["docker", "version"], timeout=30)
        if not build:
            return
        self.commands.run(
            ["docker", "pull", "ghcr.io/spongebob888/shadowquic:latest"],
            timeout=600,
        )
        self.commands.run(
            [
                "docker",
                "build",
                "--pull",
                "--no-cache",
                "-f",
                "docker/clash-rs.Dockerfile",
                "-t",
                "shadowquic-interop/clash-rs:latest",
                ".",
            ],
            timeout=1800,
        )
        self.commands.run(
            [
                "docker",
                "build",
                "--pull",
                "-f",
                "docker/quicproxy.Dockerfile",
                "-t",
                "shadowquic-interop/quicproxy:latest",
                ".",
            ],
            timeout=1800,
        )
        self.commands.run(
            [
                "docker",
                "build",
                "--pull",
                "-f",
                "docker/mihomo-meta.Dockerfile",
                "-t",
                "shadowquic-interop/mihomo-meta:latest",
                ".",
            ],
            timeout=1800,
        )
        self.commands.run(
            [
                "docker",
                "build",
                "--pull",
                "-f",
                "docker/proxypen.Dockerfile",
                "-t",
                PROXYPEN_IMAGE,
                ".",
            ],
            timeout=1800,
        )

    def run_cell(
        self,
        *,
        client: Implementation,
        server: Implementation,
        protocols: list[Protocol],
        target: str,
        work_dir: Path,
    ) -> CellResult:
        started = time.monotonic()
        suffix = uuid.uuid4().hex[:10]
        network = f"sq-interop-{suffix}"
        server_name = f"sq-server-{suffix}"
        cell_dir = work_dir / f"{client.key}_{server.key}"
        log_dir = cell_dir / "logs"
        server_config = cell_dir / "server" / server.config_name
        server_config.parent.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        server_config.write_text(server.render_server(), encoding="utf-8")

        mode_protocols: dict[bool, list[Protocol]] = {False: []}
        if Protocol.HTTP2 in protocols:
            mode_protocols[False].append(Protocol.HTTP2)
        if Protocol.HTTP3 in protocols:
            mode_protocols[False].append(Protocol.HTTP3)
            mode_protocols[True] = [Protocol.HTTP3]

        client_names: dict[bool, str] = {}
        client_configs: dict[bool, Path] = {}
        for over_stream in mode_protocols:
            mode_name = "over-stream" if over_stream else "udp"
            client_names[over_stream] = f"sq-client-{mode_name}-{suffix}"
            config = cell_dir / f"client-{mode_name}" / client.config_name
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(
                client.render_client(server_name, over_stream=over_stream),
                encoding="utf-8",
            )
            client_configs[over_stream] = config

        probes: list[ProbeResult] = []
        errors: list[str] = []
        created_network = False
        try:
            self.commands.run(["docker", "network", "create", network], timeout=30)
            created_network = True
            self._start_container(server_name, network, server, server_config)
            self._assert_running(server_name, "server")
            mode_errors: dict[bool, str] = {}
            started_modes: list[bool] = []
            for over_stream in mode_protocols:
                client_name = client_names[over_stream]
                try:
                    self._start_container(
                        client_name,
                        network,
                        client,
                        client_configs[over_stream],
                    )
                    self._assert_running(client_name, "client")
                    started_modes.append(over_stream)
                except BackendError as exc:
                    mode_errors[over_stream] = str(exc)
                    errors.append(str(exc))
            if started_modes:
                time.sleep(self.readiness_delay)
            self._assert_running(server_name, "server")
            for over_stream, mode_items in mode_protocols.items():
                client_name = client_names[over_stream]
                mode_error = mode_errors.get(over_stream)
                if mode_error is None:
                    try:
                        self._assert_running(client_name, "client")
                    except BackendError as exc:
                        mode_error = str(exc)
                        errors.append(mode_error)
                for protocol in mode_items:
                    probe_over_stream = (
                        over_stream if protocol == Protocol.HTTP3 else None
                    )
                    if mode_error is not None:
                        probes.append(
                            ProbeResult(
                                protocol=protocol,
                                status=Status.ERROR,
                                over_stream=probe_over_stream,
                                message=mode_error,
                            )
                        )
                        continue
                    try:
                        probes.append(
                            self._probe(
                                network,
                                client_name,
                                target,
                                protocol,
                                over_stream=probe_over_stream,
                            )
                        )
                    except BackendError as exc:
                        errors.append(str(exc))
                        probes.append(
                            ProbeResult(
                                protocol=protocol,
                                status=Status.ERROR,
                                over_stream=probe_over_stream,
                                message=str(exc),
                            )
                        )
        except BackendError as exc:
            errors.append(str(exc))
            completed = {(probe.protocol, probe.over_stream) for probe in probes}
            probes.extend(
                ProbeResult(
                    protocol=protocol,
                    status=Status.ERROR,
                    over_stream=over_stream,
                    message=str(exc),
                )
                for protocol, over_stream in probe_variants(protocols)
                if (protocol, over_stream) not in completed
            )
        finally:
            self._capture_logs(server_name, log_dir / "server.log")
            for over_stream, client_name in client_names.items():
                mode_name = "over-stream" if over_stream else "udp"
                self._capture_logs(client_name, log_dir / f"client-{mode_name}.log")
                self._cleanup_container(client_name)
            self._cleanup_container(server_name)
            if created_network:
                self.commands.run(
                    ["docker", "network", "rm", network], timeout=30, check=False
                )

        return CellResult(
            client=client.key,
            server=server.key,
            status=aggregate_status(probes),
            probes=probes,
            duration_ms=int((time.monotonic() - started) * 1000),
            message="; ".join(dict.fromkeys(errors)) or None,
            log_dir=str(log_dir),
        )

    def _start_container(
        self,
        name: str,
        network: str,
        implementation: Implementation,
        config: Path,
    ) -> None:
        self.commands.run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                name,
                "--network",
                network,
                "--mount",
                f"type=bind,src={config.resolve()},dst=/config/{implementation.config_name},readonly",
                implementation.image,
                *implementation.command(),
            ],
            timeout=60,
        )

    def _assert_running(self, name: str, role: str) -> None:
        result = self.commands.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            timeout=30,
            check=False,
        )
        if result.returncode != 0 or result.stdout.strip() != "true":
            logs = self.commands.run(
                ["docker", "logs", name], timeout=30, check=False
            ).output.strip()
            raise BackendError(f"{role} {name} stopped during startup: {logs[-1200:]}")

    def _probe(
        self,
        network: str,
        client_name: str,
        target: str,
        protocol: Protocol,
        *,
        over_stream: bool | None,
    ) -> ProbeResult:
        result = self.commands.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                network,
                PROXYPEN_IMAGE,
                "test",
                "--proxy",
                f"socks5://{client_name}:{SOCKS_PORT}",
                "--target",
                target,
                "--protocol",
                protocol.value,
                "--timeout",
                str(self.timeout),
            ],
            timeout=self.timeout + 15,
            check=False,
        )
        return parse_proxypen_output(
            protocol,
            result.output,
            result.returncode,
            over_stream=over_stream,
        )

    def _capture_logs(self, name: str, destination: Path) -> None:
        result = self.commands.run(
            ["docker", "logs", "--timestamps", name], timeout=30, check=False
        )
        if result.output:
            destination.write_text(result.output, encoding="utf-8")

    def _cleanup_container(self, name: str) -> None:
        self.commands.run(["docker", "rm", "--force", name], timeout=30, check=False)


_SUCCESS = re.compile(
    r"^\[(?P<protocol>HTTP/2|HTTP/3)\]\s+OK\s+(?P<status>\d{3})\s+"
    r"\((?P<duration>\d+)ms\)(?P<metrics>.*)$",
    re.MULTILINE,
)
_FAILURE = re.compile(
    r"^\[(?P<protocol>HTTP/2|HTTP/3)\]\s+FAILED:\s*(?P<message>.+)$",
    re.MULTILINE,
)
_METRIC = re.compile(r"(?P<name>socks|tcp|tls|ttfb|size):(?P<value>\d+)(?:ms|B)")


def parse_proxypen_output(
    protocol: Protocol,
    output: str,
    returncode: int,
    *,
    over_stream: bool | None = None,
) -> ProbeResult:
    success = _SUCCESS.search(output)
    if success:
        metrics = {
            item.group("name"): int(item.group("value"))
            for item in _METRIC.finditer(success.group("metrics"))
        }
        return ProbeResult(
            protocol=protocol,
            status=Status.PASS,
            over_stream=over_stream,
            http_status=int(success.group("status")),
            duration_ms=int(success.group("duration")),
            metrics=metrics,
            output=output,
        )

    failure = _FAILURE.search(output)
    if failure:
        return ProbeResult(
            protocol=protocol,
            status=Status.FAIL,
            over_stream=over_stream,
            message=failure.group("message").strip(),
            output=output,
        )

    detail = output.strip()[-1200:] or f"ProxyPen exited with status {returncode}"
    return ProbeResult(
        protocol=protocol,
        status=Status.ERROR,
        over_stream=over_stream,
        message=f"unrecognized ProxyPen output: {detail}",
        output=output,
    )
