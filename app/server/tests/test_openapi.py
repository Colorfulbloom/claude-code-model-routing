"""Tests that the committed OpenAPI file and TypeScript types are not stale."""

import json
from pathlib import Path

import openapi_export

API_DIR = Path(__file__).resolve().parents[2] / "web" / "src" / "api"
COMMITTED = API_DIR / "openapi.json"
TYPES = API_DIR / "schema.d.ts"
REGENERATE = "run the export, then `npmw --prefix app/web run api-types`"


def test_export_to_a_temp_file_equals_the_committed_file(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    openapi_export.main(["--out", str(out)])
    assert out.read_text(encoding="utf-8") == COMMITTED.read_text(encoding="utf-8"), (
        f"openapi.json is stale, {REGENERATE}"
    )


def test_export_is_sorted_two_space_with_trailing_newline() -> None:
    text = openapi_export.render_schema()
    assert text.endswith("}\n")
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def test_export_is_stable_between_runs() -> None:
    assert openapi_export.render_schema() == openapi_export.render_schema()


def test_generated_types_cover_every_path_and_schema() -> None:
    schema = json.loads(COMMITTED.read_text(encoding="utf-8"))
    types = TYPES.read_text(encoding="utf-8")
    for path in schema["paths"]:
        assert f'"{path}"' in types, f"schema.d.ts is stale, {REGENERATE}"
    for name in schema["components"]["schemas"]:
        assert name in types, f"schema.d.ts is stale, {REGENERATE}"
    for path, methods in schema["paths"].items():
        for method in methods.values():
            assert method["operationId"] in types, path


def test_export_needs_no_files_on_disk() -> None:
    schema = openapi_export.build_schema()
    assert schema["info"]["title"] == "Bar Tab"  # type: ignore[index]
    assert "/api/app" in schema["paths"]  # type: ignore[operator]
