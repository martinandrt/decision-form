#!/usr/bin/env python3
"""Build a decision form: questions in Markdown (or JSON) -> one self-contained HTML page.

    python3 build_form.py decisions.md                 # writes decisions.html next to it
    python3 build_form.py decisions.md -o out.html     # explicit output path
    python3 build_form.py data.json --lang cs          # JSON input, Czech UI
    cat data.json | python3 build_form.py - -o out.html

Markdown syntax:
    # Repo cleanup before v2.0                  -> title
    Tap a choice, then send. [Context](https://...)  -> line under the title; links go after it
    ## Wave 1 - safe, reversible                -> group heading
    ### Delete 23 merged branches?             -> question (numbered automatically)
    None has an open pull request.             -> why: what is at stake (optional, before the options)
    > Longer plain-language explanation.       -> hidden behind "Explain" (optional)
    - Delete all *                             -> option; trailing * = recommended
    - Keep some (write which) [write]          -> option with a text field
    - c) Keep all                              -> explicit option key
Option keys a, b, c... are assigned automatically. An "x) Other" option with a text field is added by
the page itself when a question has no text field.

JSON: {"title", "sub", "links": [[text, url]], "lang", "id", "groups": [{"heading", "questions": [{"title",
"why", "explanation", "options": [["a", "text", recommended, text_field]]}]}]}

Standard library only. If Node.js is installed, the page script is syntax-checked before writing.
"""
import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "template.html"
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
FIELD_MARKERS = ("[write]", "[text]")


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "decision-form"


def from_markdown(text: str) -> dict:
    d = {"title": "", "sub": "", "links": [], "groups": []}
    sub, group, question = [], None, None
    for line in text.splitlines():
        r = line.strip()
        if not r:
            continue
        if r.startswith("### "):
            if group is None:
                group = {"heading": "Decisions", "questions": []}
                d["groups"].append(group)
            question = {"title": r[4:].strip(), "why": "", "explanation": "", "options": []}
            group["questions"].append(question)
        elif r.startswith("## "):
            group, question = {"heading": r[3:].strip(), "questions": []}, None
            d["groups"].append(group)
        elif r.startswith("# "):
            d["title"] = r[2:].strip()
        elif r.startswith(">") and question is not None:
            question["explanation"] = (question["explanation"] + " " + r.lstrip(">").strip()).strip()
        elif r[:2] in ("- ", "* ") and question is not None:
            v = r[2:].strip()
            field = any(m in v for m in FIELD_MARKERS)
            for m in FIELD_MARKERS:
                v = v.replace(m, "")
            v = v.strip()
            rec = v.endswith("*")
            v = v.rstrip("*").strip()
            m = re.match(r"^([a-z])\)\s+(.*)$", v)
            key, v = (m.group(1), m.group(2)) if m else (chr(ord("a") + len(question["options"])), v)
            question["options"].append([key, v, 1 if rec else 0, 1 if field else 0])
        elif question is not None and not question["options"]:
            question["why"] = (question["why"] + " " + r).strip()
        elif group is None:
            d["links"] += LINK.findall(r)
            sub.append(LINK.sub("", r).strip())
    d["sub"] = " ".join(x for x in sub if x)
    return d


def to_form(d: dict, lang: str | None = None, form_id: str | None = None) -> dict:
    """Validate input and convert it to the compact FORM structure the template renders."""
    if not d.get("title"):
        raise ValueError("the form has no title (# Title)")
    n, groups = 0, []
    for g in d.get("groups", []):
        questions = []
        for q in g["questions"]:
            n += 1
            if not q.get("options"):
                raise ValueError(f"question {n} ({q['title']!r}) has no options")
            keys = [str(o[0]) for o in q["options"]]
            if len(set(keys)) != len(keys):
                raise ValueError(f"question {n} ({q['title']!r}) has duplicate option keys: {keys}")
            if "x" in keys and not any(len(o) > 3 and o[3] for o in q["options"]):
                raise ValueError(f"question {n}: key x is reserved for the automatic Other option")
            opts = [[str(o[0]), str(o[1]), int(bool(o[2] if len(o) > 2 else 0)), int(bool(o[3] if len(o) > 3 else 0))]
                    for o in q["options"]]
            row = [n, q["title"], q.get("why", "")]
            row.append(opts)
            if q.get("explanation"):
                row.append(q["explanation"])
            questions.append(row)
        groups.append([g["heading"], questions])
    if n == 0:
        raise ValueError("the form has no questions (### Question)")
    lang = lang or d.get("lang") or "en"
    if lang not in ("en", "cs"):
        raise ValueError(f"unsupported lang {lang!r} (en, cs)")
    return {"id": form_id or d.get("id") or slugify(d["title"]), "lang": lang, "title": d["title"],
            "sub": d.get("sub", ""), "links": [list(x) for x in d.get("links", [])], "groups": groups}


def render(form: dict, template: str | None = None) -> str:
    page = template if template is not None else TEMPLATE.read_text(encoding="utf-8")
    page = re.sub(r"<title>.*?</title>", lambda _: f"<title>{html.escape(form['title'])}</title>", page, count=1)
    page = re.sub(r'<html lang="[^"]*">', lambda _: f'<html lang="{form["lang"]}">', page, count=1)
    # "</" is escaped so text such as "</script>" inside a question cannot close the script tag.
    block = "const FORM = " + json.dumps(form, ensure_ascii=False, indent=1).replace("</", "<\\/") + ";\n"
    page, k = re.subn(r"const FORM = \{.*?\n\};\n(?=/\* FORM:END \*/)", lambda _: block, page, count=1, flags=re.S)
    if k != 1:
        raise ValueError("template is missing the FORM block (const FORM = ... /* FORM:END */)")
    return page


def check_js(page: str) -> str | None:
    """Return a syntax error message, or None when the script parses (or Node.js is not installed)."""
    js = page[page.index("<script>") + len("<script>"):page.rindex("</script>")]
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "form.js"
        f.write_text(js, encoding="utf-8")
        try:
            r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        except FileNotFoundError:
            return None
    return r.stderr[:800] if r.returncode else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build a decision form page from Markdown or JSON.",
                                 epilog="Syntax: see the module docstring (python3 build_form.py --syntax).")
    ap.add_argument("source", nargs="?", help="questions .md or .json file, or - for JSON on stdin")
    ap.add_argument("-o", "--output", help="output .html (default: next to the source)")
    ap.add_argument("--lang", choices=["en", "cs"], help="page language (default en, or lang from JSON)")
    ap.add_argument("--id", help="form id used for the browser draft (default: slug of the title)")
    ap.add_argument("--syntax", action="store_true", help="print the Markdown/JSON syntax and exit")
    a = ap.parse_args(argv)
    if a.syntax or not a.source:
        print(__doc__)
        return 0 if a.syntax else 2
    if a.source == "-":
        data, out = json.loads(sys.stdin.read()), None
    else:
        src = Path(a.source)
        text = src.read_text(encoding="utf-8")
        data = json.loads(text) if src.suffix == ".json" else from_markdown(text)
        out = src.with_suffix(".html")
    if a.output:
        out = Path(a.output)
    if out is None:
        print("error: -o is required when reading from stdin", file=sys.stderr)
        return 2
    try:
        form = to_form(data, a.lang, a.id)
        page = render(form)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    err = check_js(page)
    if err:
        print(f"error: page script does not parse\n{err}", file=sys.stderr)
        return 1
    out.write_text(page, encoding="utf-8")
    count = sum(len(g[1]) for g in form["groups"])
    print(f"{out}  ({count} questions in {len(form['groups'])} groups)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
