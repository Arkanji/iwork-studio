"""Front door (specs/002-front-door): samples, honest capabilities — headless."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from numbers_parser import Document  # noqa: E402

from iwork_studio import samples  # noqa: E402


def test_samples_copy_and_never_overwrite(tmp_path):
    out = samples.copy_samples(tmp_path / "try")
    assert len(out["copied"]) == 2 and out["try_it"]
    doc = Document(str(tmp_path / "try" / "sample-sales.numbers"))
    names = [doc.sheets[i].name for i in range(len(doc.sheets))]
    assert names == ["Sales", "المبيعات"]
    (tmp_path / "try" / "sample-outline.md").write_text("mine")
    again = samples.copy_samples(tmp_path / "try")
    assert again["copied"] == [] and len(again["skipped_existing"]) == 2
    assert (tmp_path / "try" / "sample-outline.md").read_text() == "mine"


def test_samples_ship_in_the_package():
    from importlib import resources

    files = {p.name for p in resources.files("iwork_studio").joinpath("samples").iterdir()}
    assert set(samples.SAMPLES) <= files
    pyproject = (REPO / "pyproject.toml").read_text()
    assert 'iwork_studio = ["samples/*"]' in pyproject


def test_capabilities_reports_fence_backups_and_try_it(monkeypatch, tmp_path):
    from iwork_studio import mcp_server

    monkeypatch.setenv("IWORK_STUDIO_ROOTS", str(tmp_path))
    caps = mcp_server.iwork_capabilities()
    assert caps["folder_fence"] == [str(tmp_path.resolve())]
    assert caps["backups"]["kept_per_file"] == 10 and caps["try_it"]
    assert "runnable_here" in caps["keynote_slide_ops"] and "Automation" in caps["automation"]
    monkeypatch.delenv("IWORK_STUDIO_ROOTS")
    assert "none" in mcp_server.iwork_capabilities()["folder_fence"]
