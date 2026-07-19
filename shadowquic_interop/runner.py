from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol as TypingProtocol

from . import __version__
from .adapters import Implementation
from .models import CellResult, ProbeResult, Protocol, RunResult, Status


class CellBackend(TypingProtocol):
    def prepare(self, *, build: bool = True) -> None: ...

    def run_cell(
        self,
        *,
        client: Implementation,
        server: Implementation,
        protocols: list[Protocol],
        target: str,
        work_dir: Path,
    ) -> CellResult: ...


class InteropRunner:
    def __init__(self, backend: CellBackend) -> None:
        self.backend = backend

    def run(
        self,
        *,
        clients: list[Implementation],
        servers: list[Implementation],
        protocols: list[Protocol],
        target: str,
        work_dir: Path,
        build: bool = True,
    ) -> RunResult:
        started = datetime.now(UTC)
        self.backend.prepare(build=build)
        results: list[CellResult] = []
        for client in clients:
            for server in servers:
                reason = self._unsupported_reason(client, server)
                if reason:
                    results.append(
                        CellResult(
                            client=client.key,
                            server=server.key,
                            status=Status.UNSUPPORTED,
                            probes=[
                                ProbeResult(
                                    protocol=protocol,
                                    status=Status.UNSUPPORTED,
                                    message=reason,
                                )
                                for protocol in protocols
                            ],
                            duration_ms=0,
                            message=reason,
                        )
                    )
                    continue
                results.append(
                    self.backend.run_cell(
                        client=client,
                        server=server,
                        protocols=protocols,
                        target=target,
                        work_dir=work_dir,
                    )
                )

        finished = datetime.now(UTC)
        implementations = {item.key: item for item in [*clients, *servers]}
        return RunResult(
            run_id=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            started_at=started.isoformat().replace("+00:00", "Z"),
            finished_at=finished.isoformat().replace("+00:00", "Z"),
            target=target,
            protocols=protocols,
            implementations=[item.record() for item in implementations.values()],
            results=results,
            runner_version=__version__,
        )

    @staticmethod
    def _unsupported_reason(client: Implementation, server: Implementation) -> str | None:
        if not client.client:
            return client.note or f"{client.name} has no client adapter"
        if not server.server:
            return server.note or f"{server.name} has no server adapter"
        return None


def write_result(result: RunResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = result.run_id.replace(":", "-") + ".json"
    path = output_dir / filename
    data = json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n"
    path.write_text(data, encoding="utf-8")
    (output_dir / "latest.json").write_text(data, encoding="utf-8")
    return path


def read_result(path: Path) -> RunResult:
    return RunResult.from_dict(json.loads(path.read_text(encoding="utf-8")))

