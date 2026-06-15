"""CLI: generate static team pages from the results XML.

  python -m jukola.generate --team <teamid>   one team page
  python -m jukola.generate --all             every team page
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from .analyze import analyze_team, build_field
from .parse import parse_event
from .render import render_team_page


def team_filename(teamid: str) -> str:
    return f"team_{teamid}.html"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate Jukola team insight pages.")
    ap.add_argument("--xml", default="results_j2026_ju.xml", help="source results XML")
    ap.add_argument("--out", default="out", help="output directory")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--team", help="render a single team by teamid")
    g.add_argument("--all", action="store_true", help="render every team")
    args = ap.parse_args(argv)

    t0 = time.time()
    event_name, teams = parse_event(args.xml)
    field = build_field(teams)
    os.makedirs(args.out, exist_ok=True)

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
        path = os.path.join(args.out, team_filename(team.teamid))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)

    print(f"wrote {len(targets)} page(s) to {args.out}/ in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
