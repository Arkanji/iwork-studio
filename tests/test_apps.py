"""App-name resolution (classic vs Creator Studio) — headless."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import apps  # noqa: E402


@pytest.fixture()
def fake_apps(tmp_path, monkeypatch):
    monkeypatch.setattr(apps, "_APP_DIRS", (str(tmp_path),))
    for var in ("IWORK_STUDIO_PAGES_APP", "IWORK_STUDIO_KEYNOTE_APP", "IWORK_STUDIO_NUMBERS_APP", "IWORK_STUDIO_ALLOW_CREATOR_STUDIO"):
        monkeypatch.delenv(var, raising=False)

    def install(*bundles):
        for b in bundles:
            (tmp_path / f"{b}.app").mkdir()

    return install


def test_nothing_installed_falls_back_to_classic_name(fake_apps):
    assert apps.app_name("Pages") == "Pages"


def test_classic_only(fake_apps):
    fake_apps("Pages")
    assert apps.app_name("Pages") == "Pages"


def test_both_installed_prefers_verified_classic(fake_apps):
    fake_apps("Pages", "Pages Creator Studio")
    assert apps.app_name("Pages") == "Pages"


def test_creator_studio_only_refused_loud(fake_apps):
    fake_apps("Numbers Creator Studio")
    with pytest.raises(apps.CreatorStudioUnverifiedError) as ei:
        apps.app_name("Numbers")
    assert "IWORK_STUDIO_ALLOW_CREATOR_STUDIO" in str(ei.value)


def test_keynote_creator_studio_allowed_after_live_probe(fake_apps):
    fake_apps("Keynote Creator Studio")
    assert apps.app_name("Keynote") == "Keynote Creator Studio"


def test_pages_creator_studio_allowed_after_live_run(fake_apps):
    fake_apps("Pages Creator Studio")
    assert apps.app_name("Pages") == "Pages Creator Studio"


def test_creator_studio_opt_in(fake_apps, monkeypatch):
    fake_apps("Numbers Creator Studio")
    monkeypatch.setenv("IWORK_STUDIO_ALLOW_CREATOR_STUDIO", "1")
    assert apps.app_name("Numbers") == "Numbers Creator Studio"


def test_env_override_wins(fake_apps, monkeypatch):
    fake_apps("Pages")
    monkeypatch.setenv("IWORK_STUDIO_PAGES_APP", "Pages Beta")
    assert apps.app_name("Pages") == "Pages Beta"


def test_unknown_app_rejected():
    with pytest.raises(ValueError):
        apps.app_name("Word")
