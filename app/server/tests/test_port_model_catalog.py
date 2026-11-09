"""Tests for model name matching and the catalog loader: app/server/model_catalog.py.

The two ``normalize_model`` cases come from tests/test_resolve.py. The loader tests
are new, because the old resolver had no separate loader.
"""

# ruff: noqa: PT009 - unittest style, as in the old resolver tests.
import json
import unittest
from pathlib import Path

import model_catalog

# The five name forms, in the order the old rules schema lists them.
NAME_FORMS = ("canonical", "alias", "dated", "context_1m", "provider")


class ModelNameTests(unittest.TestCase):
    CATALOG = model_catalog.load_catalog()

    def test_every_name_form(self) -> None:
        cases = [
            ("claude-opus-5-5", ("claude-opus-5-5", "canonical")),
            ("claude-opus-5", ("claude-opus-5", "canonical")),
            ("opus", ("claude-opus-5-5", "alias")),
            ("sonnet", ("claude-sonnet-5-5", "alias")),
            ("claude-opus-5-5[1m]", ("claude-opus-5-5", "context_1m")),
            ("claude-opus-5-5-20261001", ("claude-opus-5-5", "dated")),
            ("us.anthropic.claude-opus-5-5-v1:0", ("claude-opus-5-5", "provider")),
            ("claude-opus-5-5@20261001", ("claude-opus-5-5", "provider")),
            ("claude-opus-9", (None, None)),
            ("claude-opus-5-5-2026", (None, None)),
            ("opus[1m]", (None, None)),
            ("", (None, None)),
            (None, (None, None)),
            (5, (None, None)),
        ]
        for name, want in cases:
            with self.subTest(name=name):
                self.assertEqual(
                    model_catalog.normalize_model(name, self.CATALOG), want
                )

    def test_forms_match_the_schema_list(self) -> None:
        names = (
            "claude-opus-5-5",
            "opus",
            "claude-opus-5-5-20261001",
            "claude-opus-5-5[1m]",
            "claude-opus-5-5@20261001",
        )
        found = {model_catalog.normalize_model(n, self.CATALOG)[1] for n in names}
        self.assertEqual(found, set(NAME_FORMS))


class LoaderTests(unittest.TestCase):
    def test_the_default_file_is_the_bundled_rules(self) -> None:
        self.assertEqual(
            model_catalog.RULES_PATH,
            Path(model_catalog.__file__).resolve().parent / "data" / "rules.json",
        )
        rules = model_catalog.load_rules()
        self.assertEqual(set(rules), {"schema_version", "models", "variables", "rules"})

    def test_the_catalog_is_the_models_list_with_aliases(self) -> None:
        catalog = model_catalog.load_catalog()
        self.assertEqual(catalog, model_catalog.load_rules()["models"])
        ids = [m["id"] for m in catalog]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("claude-opus-5-5", ids)
        aliases = {a for m in catalog for a in m.get("aliases", [])}
        self.assertTrue({"opus", "sonnet"} <= aliases)

    def test_a_path_argument_reads_that_file(self) -> None:
        import tempfile

        doc = {"models": [{"id": "m-1", "aliases": ["short"]}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            catalog = model_catalog.load_catalog(path)
            self.assertEqual(catalog, doc["models"])
            self.assertEqual(
                model_catalog.normalize_model("short", catalog), ("m-1", "alias")
            )
            self.assertEqual(model_catalog.load_catalog(str(path)), doc["models"])

    def test_dated_and_provider_forms_need_a_catalog_id_underneath(self) -> None:
        catalog: model_catalog.Catalog = [{"id": "m-1", "aliases": []}]
        self.assertEqual(
            model_catalog.normalize_model("m-1-20260101", catalog), ("m-1", "dated")
        )
        self.assertEqual(
            model_catalog.normalize_model("m-2-20260101", catalog), (None, None)
        )
        self.assertEqual(model_catalog.normalize_model("m-1", []), (None, None))


if __name__ == "__main__":
    unittest.main()
