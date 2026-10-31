"""Checks of the end-to-end checks files and of the pure helpers in test_pages_e2e.py.

No browser starts here. Importing test_pages_e2e starts nothing, and the Chrome tests in it skip unless MR_E2E=1.
"""
import json
import os
import re
import unittest

import helpers
import test_pages_e2e as pages
import test_settings_e2e as settings_e2e

INDEX = os.path.join(helpers.REPO, "dashboard", "static", "index.html")
STRINGS_FILE = os.path.join(helpers.REPO, "dashboard", "static", "strings.json")
ROUTE_KEYS = {"hash", "texts"}
with open(STRINGS_FILE, encoding="utf-8") as _fh:
    STRINGS = json.load(_fh)


def data_pages():
    with open(INDEX, encoding="utf-8") as fh:
        return re.findall(r'<section data-page="([^"]+)"', fh.read())


class ChecksFiles(unittest.TestCase):
    def test_one_file_per_page(self):
        names = sorted(f[:-5] for f in os.listdir(pages.CHECKS_DIR) if f.endswith(".json"))
        self.assertEqual(len(data_pages()), 12)
        self.assertEqual(names, sorted(data_pages()))
        self.assertEqual([f for f in os.listdir(pages.CHECKS_DIR) if not f.endswith(".json")], [])

    def test_each_file_names_its_page(self):
        for name in data_pages():
            with open(os.path.join(pages.CHECKS_DIR, name + ".json"), encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["page"], name)

    def test_schema(self):
        for name in data_pages():
            with open(os.path.join(pages.CHECKS_DIR, name + ".json"), encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(set(data), {"page", "routes"}, name)
            self.assertIsInstance(data["routes"], list, name)
            self.assertTrue(data["routes"], name)
            for route in data["routes"]:
                self.assertEqual(set(route), ROUTE_KEYS, name)
                self.assertIsInstance(route["hash"], str, name)
                self.assertTrue(route["hash"].startswith("#/"), (name, route["hash"]))
                self.assertIsInstance(route["texts"], list, name)
                for text in route["texts"]:
                    self.assertIsInstance(text, str, name)
                    self.assertTrue(text.strip(), (name, route))

    def test_load_checks_reads_all_files_and_fills_the_session(self):
        checks = pages.load_checks()
        self.assertEqual([c["page"] for c in checks], sorted(data_pages()))
        routes = pages.routes_of(checks, "abc-123")
        detail = [r for r in routes if r[0] == "session-detail"]
        self.assertEqual([r[1] for r in detail], ["#/sessions/abc-123"])
        self.assertIn("Tidewater reporting", detail[0][2])
        self.assertEqual(sum(1 for r in routes if r[0] in ("agent-detail", "trail")), 7)
        self.assertEqual(len(routes) * len(pages.THEMES) * len(pages.WIDTHS), 128)
        self.assertFalse([r for r in routes if pages.SESSION_TOKEN in r[1]])

    def test_settings_and_trail_texts_avoid_the_forms_innertext_changes(self):
        """The sweep reads innerText, which keeps line breaks and applies text-transform. Check what needs no browser."""
        uppercased = {t.lower() for t in (STRINGS[k] for k in (
            "f_model", "f_effort", "f_cache", "f_compact", "cap", "experiment", "h_file", "h_state", "h_next"))}
        for name in ("settings", "trail", "attention", "rules", "files"):
            with open(os.path.join(pages.CHECKS_DIR, name + ".json"), encoding="utf-8") as fh:
                data = json.load(fh)
            for route in data["routes"]:
                for text in route["texts"]:
                    where = (name, route["hash"], text)
                    self.assertEqual(text, text.strip(), where)
                    self.assertNotIn("\n", text, where)
                    self.assertNotIn("  ", text, where)
                    self.assertNotIn("{", text, where)  # an unfilled slot
                    self.assertNotIn(text.lower(), uppercased, where)  # .tl-l, .ru-l and .meta dt show these in capitals


class Helpers(unittest.TestCase):
    def test_add_query(self):
        self.assertEqual(pages.add_query("#/agents", "theme", "dark"), "#/agents?theme=dark")
        self.assertEqual(pages.add_query("#/overview?project=all", "theme", "light"), "#/overview?project=all&theme=light")
        self.assertEqual(pages.add_query("#/agents/@main", "theme", "dark"), "#/agents/@main?theme=dark")

    def test_non_local_urls(self):
        urls = [
            "http://127.0.0.1:5000/", "http://127.0.0.1:5000/static/js/app.js", "data:image/png;base64,AAAA", "about:blank",
            "http://localhost:5000/", "http://127.0.0.1:5001/", "https://127.0.0.1:5000/", "https://example.com/x.js",
        ]
        self.assertEqual(pages.non_local_urls(urls, 5000), [
            "http://localhost:5000/", "http://127.0.0.1:5001/", "https://127.0.0.1:5000/", "https://example.com/x.js"])
        self.assertEqual(pages.non_local_urls([], 5000), [])

    def test_same_origin_paths(self):
        urls = ["http://127.0.0.1:5000/", "http://127.0.0.1:5000/api/usage?project=a", "http://127.0.0.1:5000/#/agents",
                "http://127.0.0.1:5001/other", "data:text/plain,x"]
        self.assertEqual(pages.same_origin_paths(urls, 5000), {"/", "/api/usage"})

    def test_log_paths(self):
        log = "GET '/' 200\nGET '/api/usage' 200\nHEAD '/static/app.css' 304\nGET \"/it's\" 404\nroute error 'KeyError'\nGET '-' 400\n"
        self.assertEqual(pages.log_paths(log), ["/", "/api/usage", "/static/app.css", "/it's"])
        self.assertEqual(pages.log_paths(""), [])

    def test_screenshot_name(self):
        self.assertEqual(pages.screenshot_name("agents", "#/agents", 1440, "dark"), "agents-agents-1440-dark.png")
        self.assertEqual(pages.screenshot_name("all-projects", "#/overview?project=all", 375, "light"),
                         "all-projects-overview-project-all-375-light.png")
        self.assertEqual(pages.screenshot_name("agent-detail", "#/agents/@main", 375, "dark"), "agent-detail-agents-main-375-dark.png")

    def test_check_scripts_are_expressions(self):
        for script in (pages.STATUS_BAD, pages.STACK_BAD, pages.LABEL_BAD, pages.HEAD_HEIGHTS,
                       settings_e2e.TEXT_CONTRAST_BAD, settings_e2e.ASSUMED_CHECK):
            self.assertTrue(script.startswith("(() =>") and script.endswith("})()"))

    def test_label_script_fills_one_page_name(self):
        self.assertEqual(pages.LABEL_BAD.count("%"), 1)
        self.assertIn("main [data-page=models] .dt td", pages.LABEL_BAD % "models")

    def test_screenshot_name_takes_a_suffix(self):
        self.assertEqual(pages.screenshot_name("models", "#/models", 375, "dark", "-full"), "models-models-375-dark-full.png")


class Gating(unittest.TestCase):
    @unittest.skipIf(os.environ.get("MR_E2E") == "1", "with MR_E2E=1 the browser class runs")
    def test_browser_class_skips_without_the_opt_in(self):
        self.assertTrue(pages.PagesE2E.__unittest_skip__)
        self.assertTrue(settings_e2e.SettingsE2E.__unittest_skip__)


if __name__ == "__main__":
    unittest.main()
