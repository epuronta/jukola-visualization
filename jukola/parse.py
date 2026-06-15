"""Stream-parse the relay results XML into Team objects."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

from .model import Leg, Split, Team, parse_time


def _int(text: Optional[str]) -> Optional[int]:
    if text is None or text == "":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_leg(el: ET.Element) -> Leg:
    splits: list[Split] = []
    # Splits are derived from cumulative-time (ct) differences. A split is only
    # meaningful between *consecutive* master controls (cn == prev_cn + 1). When
    # the cn sequence jumps, the runner's fork skipped a master control, so the
    # split into the next control spans the skip and is not comparable — we
    # blank it, exactly as the official split view does. (The source cd field
    # encodes the same thing with "-"; verified cd="-" matches cn-gaps 1:1.)
    prev_cn = 0
    prev_cum = 0
    for c in el.findall("control"):
        cn = _int(c.findtext("cn")) or 0
        cum = parse_time(c.findtext("ct"))
        consecutive = cn == prev_cn + 1
        if cum is not None and consecutive:
            diff = cum - prev_cum
            split = diff if diff >= 0 else None
        else:
            split = None
        splits.append(
            Split(
                cn=cn,
                cc=(c.findtext("cc") or "").strip(),
                dist_m=_int(c.findtext("cl")),
                cum_secs=cum,
                split_secs=split,
            )
        )
        prev_cn = cn
        if cum is not None:
            prev_cum = cum
    return Leg(
        legnro=_int(el.findtext("legnro")) or 0,
        runner=(el.findtext("nm") or "").strip(),
        course=(el.findtext("crs") or "").strip(),
        emit=(el.findtext("emit") or "").strip(),
        leg_secs=parse_time(el.findtext("result")),
        splits=splits,
    )


def parse_event(path: str) -> tuple[str, list[Team]]:
    """Return (event_name, teams). Uses iterparse and clears teams to bound memory."""
    event_name = ""
    teams: list[Team] = []
    # Pull the event name from the start, then stream team elements.
    for ev, el in ET.iterparse(path, events=("end",)):
        if el.tag == "eventname":
            event_name = (el.text or "").strip()
        elif el.tag == "team":
            team = Team(
                teamid=(el.findtext("teamid") or "").strip(),
                teamname=(el.findtext("teamname") or "").strip(),
                teamnro=(el.findtext("teamnro") or "").strip(),
                placement=_int(el.findtext("placement")),
                total_secs=parse_time(el.findtext("result")),
                legs=[_parse_leg(leg) for leg in el.findall("leg")],
            )
            teams.append(team)
            el.clear()
    return event_name, teams
