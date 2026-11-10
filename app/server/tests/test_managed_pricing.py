"""The managed ``modelPricing`` layer reaches the price feed through ``read_scope``.

Claude Code reads ``modelPricing`` from managed settings only (settings-reference), so
a user, project or local copy changes nothing. ``collect_settings.ManagedPricing`` reads
the managed files through the scope, merges them as the Settings part does, caches by a
stat signature and feeds ``price_feed.PriceSettings.managed_pricing`` (m4-build.md
section 2, task 4).
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_case_helpers as sc

import collect_settings
import price_feed
import settings_layers
import store
from store_paths import StoreLayout

PRICING = {"modelPricing": {"multiplier": 2}}


def managed(tmp_path: Path, files: dict[str, str]) -> collect_settings.ManagedPricing:
    ctx = sc.scratch(tmp_path, files)
    assert ctx.managed_dir is not None
    return collect_settings.ManagedPricing(ctx.config_dir, ctx.managed_dir)


def test_no_managed_folder_gives_none(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    assert collect_settings.ManagedPricing(ctx.config_dir, None)() is None


def test_a_missing_managed_file_gives_an_empty_document(tmp_path: Path) -> None:
    assert managed(tmp_path, {})() == {}


def test_the_managed_files_merge_as_collect_merges_them(tmp_path: Path) -> None:
    source = managed(
        tmp_path,
        {
            "managed/managed-settings.json": json.dumps(
                {"modelPricing": {"multiplier": 2, "overrides": {"a": {"input": 1}}}}
            ),
            "managed/managed-settings.d/10-more.json": json.dumps(
                {"modelPricing": {"multiplier": 3}}
            ),
        },
    )
    block = (source() or {})["modelPricing"]
    assert block["multiplier"] == 3
    assert block["overrides"] == {"a": {"input": 1}}


def test_user_project_and_local_copies_never_count(tmp_path: Path) -> None:
    text = json.dumps(PRICING)
    source = managed(
        tmp_path,
        {
            "home/.claude/settings.json": text,
            "proj/.claude/settings.json": text,
            "proj/.claude/settings.local.json": text,
        },
    )
    assert "modelPricing" not in (source() or {})


def test_the_answer_is_cached_until_a_file_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = managed(tmp_path, {"managed/managed-settings.json": json.dumps(PRICING)})
    calls: list[int] = []
    real = settings_layers.managed_settings

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(settings_layers, "managed_settings", counting)
    assert (source() or {})["modelPricing"]["multiplier"] == 2
    assert (source() or {})["modelPricing"]["multiplier"] == 2
    assert len(calls) == 1
    (tmp_path / "managed" / "managed-settings.json").write_text(
        json.dumps({"modelPricing": {"multiplier": 5}}), encoding="utf-8"
    )
    assert (source() or {})["modelPricing"]["multiplier"] == 5
    assert len(calls) == 2


def test_a_file_added_to_the_folder_is_seen(tmp_path: Path) -> None:
    source = managed(tmp_path, {"managed/managed-settings.json": json.dumps(PRICING)})
    assert (source() or {})["modelPricing"]["multiplier"] == 2
    (tmp_path / "managed" / "managed-settings.d").mkdir()
    (tmp_path / "managed" / "managed-settings.d" / "z.json").write_text(
        json.dumps({"modelPricing": {"multiplier": 4}}), encoding="utf-8"
    )
    assert (source() or {})["modelPricing"]["multiplier"] == 4


def test_a_bad_managed_file_gives_an_empty_layer_not_a_crash(tmp_path: Path) -> None:
    source = managed(tmp_path, {"managed/managed-settings.json": "{not json"})
    assert price_feed.model_pricing_from(source()).empty


def test_the_settings_part_shows_modelpricing_managed_only(tmp_path: Path) -> None:
    ctx = sc.scratch(
        tmp_path,
        {
            "managed/managed-settings.json": json.dumps(PRICING),
            "home/.claude/settings.json": json.dumps(
                {"modelPricing": {"multiplier": 9}}
            ),
        },
    )
    item = {
        i.id: i for i in collect_settings.COLLECTOR.read(ctx, {}).items["settings"]
    }["settings:modelPricing"]
    assert [(s.scope, s.status) for s in item.sources] == [
        ("managed", "in_effect"),
        ("user", "ignored"),
    ]
    assert item.scope == "managed"
    assert [r.scope for r in item.reach] == ["managed"]


def test_an_ignored_modelpricing_with_no_managed_copy_is_not_as_set(
    tmp_path: Path,
) -> None:
    ctx = sc.scratch(
        tmp_path,
        {"home/.claude/settings.json": json.dumps({"modelPricing": {"multiplier": 9}})},
    )
    got = collect_settings.COLLECTOR.read(ctx, {})
    item = {i.id: i for i in got.items["settings"]}["settings:modelPricing"]
    assert item.status == "ignored"
    assert item.scope is None
    assert [(r.group, r.code, r.item_id) for r in got.problems] == [
        ("not_as_set", "ignored", "settings:modelPricing")
    ]


def test_model_pricing_from_matches_the_file_reader(tmp_path: Path) -> None:
    path = tmp_path / "managed-settings.json"
    path.write_text(
        json.dumps(
            {
                "modelPricing": {
                    "multiplier": 1.5,
                    "overrides": {
                        "claude-opus-5-5": {
                            "input": 1,
                            "output": 2,
                            "cacheRead": 0.1,
                            "cacheWrite": 1.5,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    from_file = price_feed.model_pricing_layer(path)
    from_data = price_feed.model_pricing_from(json.loads(path.read_text("utf-8")))
    assert from_file == from_data
    assert not from_data.empty
    assert price_feed.model_pricing_from(None).empty


def test_the_price_table_takes_the_managed_layer(tmp_path: Path) -> None:
    layout = StoreLayout(tmp_path / "store" / "bartab")
    conn = store.open_writer(layout)
    store.migrate(conn)
    conn.close()
    reader = store.open_reader(layout)
    try:
        plain = price_feed.price_table(
            reader, price_feed.PriceSettings(layout), now=1_800_000_000.0
        )
        ctx = sc.scratch(
            tmp_path / "world", {"managed/managed-settings.json": json.dumps(PRICING)}
        )
        assert ctx.managed_dir is not None
        settings = price_feed.PriceSettings(
            layout,
            managed_pricing=collect_settings.ManagedPricing(
                ctx.config_dir, ctx.managed_dir
            ),
        )
        layered = price_feed.price_table(reader, settings, now=1_800_000_000.0)
    finally:
        reader.close()
    assert layered.hash != plain.hash
    models: dict[str, Any] = plain.document["models"]
    name = next(iter(models))
    assert layered.document["models"][name]["input"] == pytest.approx(
        models[name]["input"] * 2
    )
