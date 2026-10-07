"""Static checks on the published site.

There is no build step, so a typo in a page's `data-sky` JSON, a missing
asset or an over-long module only shows up in a browser. These tests read the
HTML as text and check the contracts journey.js and the copy rules rely on."""
import html
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"
PAGES = [SITE / "index.html", SITE / "finance" / "index.html"]
ALL_HTML = sorted(SITE.rglob("*.html"))


class _Collector(HTMLParser):
    """Collects body attributes, sky-band videos and every local asset URL."""

    def __init__(self):
        super().__init__()
        self.body = {}
        self.bands = []
        self.local_urls = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "body":
            self.body = a
        if tag == "video" and "sky-band" in (a.get("class") or "").split():
            self.bands.append({"poster": a.get("poster"), "sources": []})
        if tag == "source" and self.bands and a.get("data-src"):
            self.bands[-1]["sources"].append(a["data-src"])
        for key in ("href", "src", "data-src", "poster"):
            value = a.get(key)
            if value and value.startswith("/"):
                self.local_urls.append(value)


def parse(path):
    c = _Collector()
    c.feed(path.read_text())
    return c


def resolve(url):
    """Map a root-absolute URL to the file the static host would serve."""
    path = SITE / url.split("#")[0].split("?")[0].lstrip("/")
    return path / "index.html" if url.endswith("/") else path


def words(fragment):
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split()


class SkyConfigTests(unittest.TestCase):
    def test_sky_config_matches_band_videos(self):
        for page in PAGES:
            with self.subTest(page=page.relative_to(SITE).as_posix()):
                c = parse(page)
                sky = json.loads(c.body["data-sky"])
                self.assertEqual(len(sky), len(c.bands), "one data-sky entry per .sky-band video")
                untils = [b["until"] for b in sky]
                self.assertEqual(untils, sorted(untils), "until fractions must increase")
                self.assertTrue(all(0 < u <= 1 for u in untils))
                self.assertEqual(untils[-1], 1, "last band must run to the end of the flight")
                for entry, video in zip(sky, c.bands):
                    self.assertTrue(video["poster"].endswith(f"/{entry['band']}.jpg"))
                    self.assertEqual(sorted(Path(s).name for s in video["sources"]),
                                     [f"{entry['band']}.mp4", f"{entry['band']}.webm"])

    def test_body_config_is_valid(self):
        themes = {}
        for page in PAGES:
            body = parse(page).body
            themes[page.parent.name] = body["data-theme"]
            self.assertGreater(int(body["data-peak-alt"]), 0)
        self.assertEqual(sorted(themes.values()), ["day", "night"])

    def test_every_manifest_band_has_published_assets(self):
        manifest = json.loads((REPO / "scripts" / "sky-manifest.json").read_text())
        ids = [b["id"] for b in manifest["bands"]]
        self.assertEqual(len(ids), len(set(ids)), "band ids must be unique")
        used = {e["band"] for p in PAGES for e in json.loads(parse(p).body["data-sky"])}
        self.assertEqual(used, set(ids), "pages and manifest must name the same bands")
        for band in manifest["bands"]:
            self.assertTrue(band["image_prompt"].strip() and band["video_prompt"].strip())
            for ext in ("mp4", "webm", "jpg"):
                self.assertTrue((SITE / "assets" / "sky" / f"{band['id']}.{ext}").is_file(),
                                f"{band['id']}.{ext} missing")

    def test_video_files_within_size_budget(self):
        # Budgets from process-video.sh: mp4 <= 2.5 MB, webm <= 1.6 MB.
        sky = SITE / "assets" / "sky"
        for path in sorted(sky.glob("*.mp4")):
            self.assertLessEqual(path.stat().st_size, 2560 * 1024, path.name)
        for path in sorted(sky.glob("*.webm")):
            self.assertLessEqual(path.stat().st_size, 1638 * 1024, path.name)


class LinkTests(unittest.TestCase):
    def test_every_local_asset_and_link_exists(self):
        self.assertGreater(len(ALL_HTML), 0)
        for page in ALL_HTML:
            for url in parse(page).local_urls:
                with self.subTest(page=page.relative_to(SITE).as_posix(), url=url):
                    self.assertTrue(resolve(url).is_file(), f"{url} does not resolve inside site/")

    def test_redirect_targets_exist(self):
        rules = [l.split() for l in (SITE / "_redirects").read_text().splitlines()
                 if l.strip() and not l.startswith("#")]
        self.assertGreater(len(rules), 0)
        for source, target, status in rules:
            self.assertIn(status, {"301", "302"})
            self.assertTrue(resolve(target).is_file(), f"{source} -> {target}")


class CopyLimitTests(unittest.TestCase):
    """CLAUDE.md: heading <= 6 words, body <= 40 words, <= 3 arrow bullets,
    so each module can be read in its dwell window."""

    def test_modules_respect_copy_limits(self):
        for page in PAGES:
            sections = re.findall(r'<section class="module[^"]*"[^>]*>(.*?)</section>', page.read_text(), re.S)
            self.assertGreater(len(sections), 0)
            for body in sections:
                heading = re.search(r"<h[12][^>]*>(.*?)</h[12]>", body, re.S)
                label = " ".join(words(heading.group(1))) if heading else "(no heading)"
                with self.subTest(page=page.parent.name, module=label):
                    self.assertIsNotNone(heading)
                    self.assertLessEqual(len(words(heading.group(1))), 6)
                    paragraph_words = sum(len(words(p)) for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S))
                    self.assertLessEqual(paragraph_words, 40)
                    self.assertLessEqual(len(re.findall(r"<li\b", body)), 3)


if __name__ == "__main__":
    unittest.main()
