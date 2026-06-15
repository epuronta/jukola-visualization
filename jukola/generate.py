"""CLI: generate static team pages from a results XML.

Output layout (one directory per event, ready for GitHub Pages):

    docs/<year>/<relay>/<teamid>.html

  python -m jukola.generate --team <teamid>   one team page
  python -m jukola.generate --all             every team page

Year and relay are inferred from the event name / filename but can be
overridden. The generator is relay-agnostic: leg count comes from the data, so
the 7-leg Jukola and the 4-leg Venla are handled the same way.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time

from .analyze import analyze_team, build_field
from .parse import parse_event
from .render import render_team_page

RELAYS = ("jukola", "venla")


def infer_year(event_name: str, xml_path: str) -> str | None:
    for src in (event_name, os.path.basename(xml_path)):
        m = re.search(r"(19|20)\d{2}", src)
        if m:
            return m.group(0)
    return None


def infer_relay(event_name: str, xml_path: str) -> str:
    hay = f"{event_name} {os.path.basename(xml_path)}".lower()
    if "venla" in hay or re.search(r"_ve\b|_ve[._]", hay):
        return "venla"
    return "jukola"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate Jukola/Venla team pages.")
    ap.add_argument("--xml", default="results_j2026_ju.xml", help="source results XML")
    ap.add_argument("--docs", default="docs", help="base output directory")
    ap.add_argument("--year", help="event year (default: inferred)")
    ap.add_argument("--relay", choices=RELAYS, help="relay (default: inferred)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--team", help="render a single team by teamid")
    g.add_argument("--all", action="store_true", help="render every team")
    args = ap.parse_args(argv)

    t0 = time.time()
    event_name, teams = parse_event(args.xml)
    field = build_field(teams)

    year = args.year or infer_year(event_name, args.xml)
    if not year:
        print("could not infer year; pass --year", file=sys.stderr)
        return 1
    relay = args.relay or infer_relay(event_name, args.xml)

    out_dir = os.path.join(args.docs, year, relay)
    os.makedirs(out_dir, exist_ok=True)

    if args.team:
        team = next((t for t in teams if t.teamid == args.team), None)
        if team is None:
            print(f"no team with teamid={args.team!r}", file=sys.stderr)
            return 1
        targets = [team]
    else:
        targets = teams

    for team in targets:
        html = render_team_page(analyze_team(team, field), event_name)
        with open(os.path.join(out_dir, f"{team.teamid}.html"), "w", encoding="utf-8") as fh:
            fh.write(html)

    print(f"wrote {len(targets)} page(s) to {out_dir}/ in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
