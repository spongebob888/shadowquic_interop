import json
import tempfile
import unittest
from pathlib import Path

from shadowquic_interop.adapters import IMPLEMENTATIONS
from shadowquic_interop.models import CellResult, ProbeResult, Protocol, Status
from shadowquic_interop.runner import InteropRunner, read_result, write_result


class FakeBackend:
    def __init__(self) -> None:
        self.prepared = None
        self.calls = []

    def prepare(self, *, build: bool = True) -> None:
        self.prepared = build

    def run_cell(self, **kwargs) -> CellResult:
        self.calls.append(kwargs)
        probes = [
            ProbeResult(protocol=item, status=Status.PASS, http_status=200)
            for item in kwargs["protocols"]
        ]
        return CellResult(
            client=kwargs["client"].key,
            server=kwargs["server"].key,
            status=Status.PASS,
            probes=probes,
            duration_ms=12,
        )


class RunnerTests(unittest.TestCase):
    def test_matrix_runs_supported_cell_and_retains_unsupported_cells(self) -> None:
        backend = FakeBackend()
        implementations = list(IMPLEMENTATIONS.values())
        result = InteropRunner(backend).run(
            clients=implementations,
            servers=implementations,
            protocols=[Protocol.HTTP2, Protocol.HTTP3],
            target="https://example.com/",
            work_dir=Path("work"),
            build=False,
        )
        self.assertFalse(backend.prepared)
        self.assertEqual(len(result.results), 9)
        self.assertEqual(len(backend.calls), 4)
        mihomo_cells = [
            cell
            for cell in result.results
            if "mihomo" in (cell.client, cell.server)
        ]
        self.assertEqual(len(mihomo_cells), 5)
        self.assertTrue(all(cell.status == Status.UNSUPPORTED for cell in mihomo_cells))

    def test_result_round_trip(self) -> None:
        backend = FakeBackend()
        shadowquic = IMPLEMENTATIONS["shadowquic"]
        result = InteropRunner(backend).run(
            clients=[shadowquic],
            servers=[shadowquic],
            protocols=[Protocol.HTTP2],
            target="https://example.com/",
            work_dir=Path("work"),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = write_result(result, Path(directory))
            loaded = read_result(path)
            self.assertEqual(loaded.run_id, result.run_id)
            self.assertEqual(loaded.results[0].probes[0].protocol, Protocol.HTTP2)
            latest = json.loads((Path(directory) / "latest.json").read_text())
            self.assertEqual(latest["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()

