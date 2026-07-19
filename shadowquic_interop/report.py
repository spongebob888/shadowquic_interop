from __future__ import annotations

import json
import shutil
from pathlib import Path

from .runner import read_result


def generate_site(
    *, results_dir: Path, output_dir: Path, web_dir: Path | None = None
) -> int:
    web_dir = web_dir or Path(__file__).resolve().parent.parent / "web"
    runs = {}
    if results_dir.exists():
        for path in sorted(results_dir.glob("*.json")):
            try:
                run = read_result(path)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            runs[run.run_id] = run.to_dict()

    ordered = sorted(runs.values(), key=lambda item: item["started_at"], reverse=True)
    template = (web_dir / "index.html").read_text(encoding="utf-8")
    payload = json.dumps(ordered, separators=(",", ":")).replace("</", "<\\/")
    html = template.replace("__SHADOWQUIC_RUN_DATA__", payload)

    output_dir.mkdir(parents=True, exist_ok=True)
    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    for name in ("app.js", "style.css"):
        shutil.copyfile(web_dir / name, assets / name)
    (output_dir / ".nojekyll").write_text("", encoding="ascii")
    return len(ordered)

