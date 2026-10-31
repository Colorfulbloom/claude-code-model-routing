"""Check the code.claude.com anchors the dashboard cites.

The offline test always runs. The live test fetches each page once and needs
MR_DOCS_LIVE=1, so the default suite never touches the network.
"""
import os
import re
import unittest
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = ("dashboard/rules.json", "dashboard/agent_fields.json", "dashboard/reference_copy.md")
URL_RE = re.compile(r"https://code\.claude\.com/docs/[^\s)\"'\]>]*#[^\s)\"'\]>]*")
FRAGMENT_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
ID_RE = re.compile(r"""\bid=["']([^"']+)["']""")

# Anchors a page sets by script, so they are not an id="..." in the rendered HTML.
# Map "path#fragment" to the reason. Empty because every cited anchor is a plain id.
KNOWN_IDS = {}


def cited_urls():
    """Return a list of (path, line number, url) for every docs URL with a fragment."""
    found = []
    for rel in SOURCES:
        with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                for url in URL_RE.findall(line):
                    found.append((rel, n, url.rstrip(".,;")))
    return found


def split_url(url):
    page, _, fragment = url.partition("#")
    return page, fragment


class AnchorFormatTest(unittest.TestCase):
    def test_some_urls_are_cited(self):
        self.assertTrue(cited_urls())

    def test_every_fragment_is_lowercase_with_hyphens(self):
        for rel, n, url in cited_urls():
            fragment = split_url(url)[1]
            with self.subTest(where="%s:%d" % (rel, n), url=url):
                self.assertTrue(fragment, "empty fragment")
                self.assertRegex(fragment, FRAGMENT_RE.pattern + r"\Z")


@unittest.skipUnless(os.environ.get("MR_DOCS_LIVE") == "1", "set MR_DOCS_LIVE=1 to fetch the docs")
class AnchorLiveTest(unittest.TestCase):
    def test_every_fragment_is_an_id_on_the_page(self):
        cache = {}
        for rel, n, url in cited_urls():
            page, fragment = split_url(url)
            if page not in cache:
                req = urllib.request.Request(page, headers={"User-Agent": "mr-doc-anchors-test"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    html = resp.read().decode("utf-8", "replace")
                cache[page] = set(ID_RE.findall(html))
            with self.subTest(where="%s:%d" % (rel, n), url=url):
                key = page.replace("https://code.claude.com", "") + "#" + fragment
                if fragment in cache[page] or key in KNOWN_IDS or (page + "#" + fragment) in KNOWN_IDS:
                    continue
                self.fail("no id=%r on %s" % (fragment, page))


if __name__ == "__main__":
    unittest.main()
