"""CLI: build index pages for the generated docs/ tree.

The team generator writes pages at docs/<year>/<relay>/<teamid>.html and links
back to a sibling index.html ("all teams") that nothing produced yet. This walks
whatever has been generated and writes those indexes:

    docs/<year>/<relay>/index.html   one entry per team page, by name
    docs/index.html                  one entry per event

Deliberately dumb: it reads the team name out of each page's <title> rather than
re-parsing the source XML, so the index only ever lists what is actually
published. Run it after the generator.

    python -m jukola.index --docs docs
"""

from __future__ import annotations

import argparse
import os
import re
from html import escape, unescape

from .render import ANALYTICS, COFFEE

# First <title> in document order is the page <title>; the per-point SVG
# <title> tooltips come later, so a non-greedy first match is the page title.
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
_BIB_RE = re.compile(r'<span class="bib">#([^<]+)</span>')


def _read_page(path: str) -> tuple[str, str | None, str | None]:
    """Return (team_name, bib, event_name) for one generated team page."""
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    name = os.path.splitext(os.path.basename(path))[0]
    event = None
    m = _TITLE_RE.search(html)
    if m:
        # title is "<team> — <event>"; em dash matches the renderer.
        team, _, ev = unescape(m.group(1)).partition(" — ")
        name = team.strip() or name
        event = ev.strip() or None
    bib = None
    b = _BIB_RE.search(html)
    if b:
        bib = unescape(b.group(1)).strip()
    return name, bib, event


def _event_pages(event_dir: str) -> list[tuple[str, str, str | None]]:
    """List (filename, team_name, bib) for team pages in one event dir."""
    out = []
    for fn in os.listdir(event_dir):
        if not fn.endswith(".html") or fn == "index.html":
            continue
        name, bib, _ = _read_page(os.path.join(event_dir, fn))
        out.append((fn, name, bib))
    # sort by team number (bib) numerically, name as fallback/tiebreaker
    def _key(row: tuple[str, str, str | None]) -> tuple[int, int, str]:
        _, name, bib = row
        if bib and bib.isdigit():
            return (0, int(bib), name.lower())
        return (1, 0, name.lower())
    out.sort(key=_key)
    return out


def _event_name(event_dir: str, year: str, relay: str) -> str:
    """Best-effort event title: take it from the first page that has one."""
    for fn in os.listdir(event_dir):
        if fn.endswith(".html") and fn != "index.html":
            _, _, ev = _read_page(os.path.join(event_dir, fn))
            if ev:
                return ev
    return f"{relay.title()} {year}"


def render_event_index(event_name: str, rows: list[tuple[str, str, str | None]]) -> str:
    items = "\n".join(
        f'    <li><a href="{escape(fn)}">{escape(name)}</a>'
        + (f' <span class="bib">#{escape(bib)}</span>' if bib else "")
        + "</li>"
        for fn, name, bib in rows
    )
    count = f"{len(rows)} team{'s' if len(rows) != 1 else ''}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(event_name)}</title>
<link rel="stylesheet" href="../../index.css">{ANALYTICS}</head>
<body>
{COFFEE}
<header>
  <div class="crumb"><a href="../../index.html">← all events</a></div>
  <h1>{escape(event_name)}</h1>
  <p class="muted">{count}</p>
</header>
<main><ul class="teams">
{items}
</ul></main>
</body></html>"""


def render_root_index(events: list[tuple[str, str, int]]) -> str:
    items = "\n".join(
        f'    <li><a href="{escape(href)}">{escape(name)}</a>'
        f' <span class="muted">— {n} team{"s" if n != 1 else ""}</span></li>'
        for href, name, n in events
    )
    body = (
        f'<ul class="events">\n{items}\n</ul>'
        if events
        else '<p class="muted">Nothing generated yet.</p>'
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jukola Visualization</title>
<link rel="stylesheet" href="index.css">{ANALYTICS}</head>
<body>
{COFFEE}
<header>
  <h1>Jukola Visualization</h1>
  <p class="muted">Static reports for Jukola orienteering relay results.</p>
</header>
<main>{body}</main>
</body></html>"""


def build(docs: str) -> int:
    """Write all index pages. Returns the number of events indexed."""
    events: list[tuple[str, str, int]] = []
    for year in sorted(os.listdir(docs)):
        ydir = os.path.join(docs, year)
        if not (year.isdigit() and os.path.isdir(ydir)):
            continue
        for relay in sorted(os.listdir(ydir)):
            edir = os.path.join(ydir, relay)
            if not os.path.isdir(edir):
                continue
            rows = _event_pages(edir)
            if not rows:
                continue
            event_name = _event_name(edir, year, relay)
            with open(os.path.join(edir, "index.html"), "w", encoding="utf-8") as fh:
                fh.write(render_event_index(event_name, rows))
            events.append((f"{year}/{relay}/index.html", event_name, len(rows)))

    with open(os.path.join(docs, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(render_root_index(events))
    return len(events)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build index pages for docs/.")
    ap.add_argument("--docs", default="docs", help="base output directory")
    args = ap.parse_args(argv)
    n = build(args.docs)
    print(f"indexed {n} event(s) under {args.docs}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
