"""Drift tests for the data files copied from the old dashboard.

``app/server/data/rules.json`` and ``app/server/data/prices-old.json`` are byte
copies of ``dashboard/rules.json`` and ``dashboard/prices.json``. When the old
files change, these tests fail until the copies are refreshed.
"""

from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
REPO_ROOT = Path(__file__).resolve().parents[3]


def test_rules_json_equals_the_dashboard_file_byte_for_byte() -> None:
    old = (REPO_ROOT / "dashboard" / "rules.json").read_bytes()
    assert (DATA / "rules.json").read_bytes() == old


def test_prices_old_json_equals_the_dashboard_prices_byte_for_byte() -> None:
    old = (REPO_ROOT / "dashboard" / "prices.json").read_bytes()
    assert (DATA / "prices-old.json").read_bytes() == old


def test_the_default_loaders_read_from_the_data_folder() -> None:
    import model_catalog
    import prices

    assert model_catalog.RULES_PATH == DATA / "rules.json"
    assert prices.PRICES_PATH == DATA / "prices-old.json"
    assert prices.check(prices.load_prices(), model_catalog.load_catalog()) == []
