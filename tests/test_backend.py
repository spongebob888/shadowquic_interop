import tempfile
import unittest
from pathlib import Path

from shadowquic_interop.adapters import IMPLEMENTATIONS
from shadowquic_interop.backend import (
    BackendError,
    CommandResult,
    DockerBackend,
    PROXYPEN_IMAGE,
    parse_proxypen_output,
)
from shadowquic_interop.models import Protocol, Status


class ProxyPenParserTests(unittest.TestCase):
    def test_success(self) -> None:
        result = parse_proxypen_output(
            Protocol.HTTP2,
            "Testing proxy ...\n\n[HTTP/2]   OK 200 (493ms) socks:4ms tls:88ms ttfb:251ms size:1400B\n",
            0,
        )
        self.assertEqual(result.status, Status.PASS)
        self.assertEqual(result.http_status, 200)
        self.assertEqual(result.duration_ms, 493)
        self.assertEqual(result.metrics["socks"], 4)
        self.assertEqual(result.metrics["size"], 1400)

    def test_failure(self) -> None:
        result = parse_proxypen_output(
            Protocol.HTTP3,
            "[HTTP/3]   FAILED: SOCKS UDP associate rejected\n",
            1,
        )
        self.assertEqual(result.status, Status.FAIL)
        self.assertEqual(result.message, "SOCKS UDP associate rejected")

    def test_unrecognized_output_is_infrastructure_error(self) -> None:
        result = parse_proxypen_output(Protocol.HTTP3, "panic: unavailable", 101)
        self.assertEqual(result.status, Status.ERROR)
        self.assertIn("panic: unavailable", result.message or "")


class PartialCellTests(unittest.TestCase):
    def test_later_probe_error_cannot_leave_cell_passing(self) -> None:
        class FakeCommands:
            probe_count = 0

            def run(self, args, *, timeout, check=True):
                command = list(args)
                if command[:2] == ["docker", "inspect"]:
                    return CommandResult(command, 0, "true\n", "")
                if PROXYPEN_IMAGE in command:
                    self.probe_count += 1
                    if self.probe_count == 1:
                        return CommandResult(
                            command, 0, "[HTTP/2] OK 200 (20ms) ttfb:10ms\n", ""
                        )
                    raise BackendError("HTTP/3 probe timed out")
                return CommandResult(command, 0, "", "")

        backend = DockerBackend(command_runner=FakeCommands(), readiness_delay=0)
        implementation = IMPLEMENTATIONS["quicproxy"]
        with tempfile.TemporaryDirectory() as directory:
            result = backend.run_cell(
                client=implementation,
                server=implementation,
                protocols=[Protocol.HTTP2, Protocol.HTTP3],
                target="https://example.com/",
                work_dir=Path(directory),
            )
        self.assertEqual(result.status, Status.ERROR)
        self.assertEqual([item.status for item in result.probes], [Status.PASS, Status.ERROR])
        self.assertEqual(result.probes[1].message, "HTTP/3 probe timed out")


class PrepareTests(unittest.TestCase):
    def test_prepares_endpoint_images(self) -> None:
        class RecordingCommands:
            def __init__(self) -> None:
                self.calls = []

            def run(self, args, *, timeout, check=True):
                command = list(args)
                self.calls.append(command)
                return CommandResult(command, 0, "", "")

        commands = RecordingCommands()
        DockerBackend(command_runner=commands).prepare()
        flattened = [" ".join(call) for call in commands.calls]
        self.assertTrue(
            any(
                "docker/mihomo-meta.Dockerfile" in call
                and "shadowquic-interop/mihomo-meta:latest" in call
                for call in flattened
            )
        )
        self.assertIn(
            "docker pull ghcr.io/watfaq/clash-rs:latest",
            flattened,
        )


if __name__ == "__main__":
    unittest.main()
