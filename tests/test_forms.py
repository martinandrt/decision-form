"""Tests for build_form.py and serve_form.py. Run: python3 -m unittest discover tests"""
import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "decision-form" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_form  # noqa: E402

MD = """# Pick a stack
Tap a choice. [Notes](https://example.com/notes)

## Wave 1
### Database?
Postgres is what the team knows.
> Longer explanation here.
- Postgres *
- SQLite
- c) Something else (write which) [write]

### Hosting?
- Fly
- Render *
"""


def form_json(page: str) -> dict:
    block = page.split("const FORM = ", 1)[1].split(";\n/* FORM:END */", 1)[0]
    return json.loads(block.replace("<\\/", "</"))


class BuildTest(unittest.TestCase):
    def test_markdown_structure(self):
        d = build_form.from_markdown(MD)
        self.assertEqual(d["title"], "Pick a stack")
        self.assertEqual(d["sub"], "Tap a choice.")
        self.assertEqual(d["links"], [("Notes", "https://example.com/notes")])
        q1, q2 = d["groups"][0]["questions"]
        self.assertEqual(q1["why"], "Postgres is what the team knows.")
        self.assertEqual(q1["explanation"], "Longer explanation here.")
        self.assertEqual(q1["options"], [["a", "Postgres", 1, 0], ["b", "SQLite", 0, 0],
                                         ["c", "Something else (write which)", 0, 1]])
        self.assertEqual(q2["options"], [["a", "Fly", 0, 0], ["b", "Render", 1, 0]])

    def test_questions_numbered_across_groups(self):
        md = "# T\n## A\n### One\n- x1\n## B\n### Two\n- y1\n"
        form = build_form.to_form(build_form.from_markdown(md))
        self.assertEqual([q[0] for _, qs in form["groups"] for q in qs], [1, 2])

    def test_render_escapes_title_and_script_breakout(self):
        d = build_form.from_markdown("# A <b> & </script> test\n### Q </script><img src=x>\n- ok\n")
        page = build_form.render(build_form.to_form(d))
        self.assertIn("<title>A &lt;b&gt; &amp; &lt;/script&gt; test</title>", page)
        self.assertEqual(page.count("</script>"), 1)  # only the real closing tag
        self.assertEqual(form_json(page)["groups"][0][1][0][1], "Q </script><img src=x>")

    def test_lang_and_id(self):
        form = build_form.to_form(build_form.from_markdown(MD), lang="cs", form_id="abc")
        self.assertEqual((form["lang"], form["id"]), ("cs", "abc"))
        page = build_form.render(form)
        self.assertIn('<html lang="cs">', page)

    def test_errors(self):
        with self.assertRaisesRegex(ValueError, "no options"):
            build_form.to_form(build_form.from_markdown("# T\n### Q without options\n"))
        with self.assertRaisesRegex(ValueError, "no questions"):
            build_form.to_form(build_form.from_markdown("# T\n"))
        with self.assertRaisesRegex(ValueError, "no title"):
            build_form.to_form(build_form.from_markdown("### Q\n- a\n"))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_form.to_form(build_form.from_markdown("# T\n### Q\n- a) one\n- a) two\n"))
        with self.assertRaisesRegex(ValueError, "reserved"):
            build_form.to_form(build_form.from_markdown("# T\n### Q\n- x) one\n"))

    def test_cli_writes_next_to_source_and_page_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "stack.md"
            src.write_text(MD, encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPTS / "build_form.py"), str(src)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            page = (Path(tmp) / "stack.html").read_text(encoding="utf-8")
            self.assertIsNone(build_form.check_js(page))
            self.assertNotIn("googleapis", page)  # no external requests

    def test_cli_rejects_bad_input_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "bad.md"
            src.write_text("# T\n### Q\n", encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPTS / "build_form.py"), str(src)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertFalse((Path(tmp) / "bad.html").exists())


class ServeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.page = Path(self.tmp.name) / "f.html"
        self.page.write_text(build_form.render(build_form.to_form(build_form.from_markdown(MD))), encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-u", str(SCRIPTS / "serve_form.py"), str(self.page), "--timeout", "0.5"],
                                     stdout=subprocess.PIPE, text=True)
        line = self.proc.stdout.readline()
        self.assertTrue(line.startswith("Open: "), line)
        self.url = line.split("Open: ", 1)[1].strip()
        self.base, self.token = self.url.split("/?t=")

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.stdout.close()
        self.proc.wait()
        self.tmp.cleanup()

    def status(self, url, data=None):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read(), e.headers

    def test_token_required_and_answers_saved(self):
        self.assertEqual(self.status(self.base + "/")[0], 403)
        self.assertEqual(self.status(self.base + "/?t=wrong")[0], 403)
        code, body, headers = self.status(self.url)
        self.assertEqual(code, 200)
        self.assertIn(b"Pick a stack", body)
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(self.status(self.base + "/answers?t=wrong", b'{"answers": {"1": "a"}}')[0], 403)
        self.assertEqual(self.status(self.base + "/answers?t=" + self.token, b'{"answers": {}}')[0], 400)
        payload = {"answers": {"1": "c", "2": "b"}, "notes": {"1": "CockroachDB"}, "code": "1c: CockroachDB 2b",
                   "readable": [{"question": 1, "title": "Database?", "choice": "c",
                                 "option": "Something else (write which)", "note": "CockroachDB"}]}
        self.assertEqual(self.status(self.base + "/answers?t=" + self.token, json.dumps(payload).encode())[0], 200)
        out = self.proc.stdout.read()
        self.assertEqual(self.proc.wait(timeout=5), 0)
        self.assertIn("Answers: 1c: CockroachDB 2b", out)
        saved = json.loads((Path(self.tmp.name) / "f.answers.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["answers"], {"1": "c", "2": "b"})
        self.assertIn("received_at", saved)

    def test_timeout_exit_code(self):
        self.proc.stdout.read()
        self.assertEqual(self.proc.wait(timeout=60), 2)
        self.assertFalse((Path(self.tmp.name) / "f.answers.json").exists())


if __name__ == "__main__":
    unittest.main()
