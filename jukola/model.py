"""Data model and time helpers.

Field semantics in the source XML (verified against the data):
  team.teamid   unique id (USE THIS as key; teamnro is a non-unique bib group)
  team.teamnro  start-group / bib number, repeats across teams
  team.result   final time "h:mm:ss", only for ranked teams
  team.placement final placement, absent for DNF/unranked teams
  leg.legnro    leg number 1..7
  leg.nm        runner name
  leg.crs       course/fork code (Jukola uses forking)
  leg.result    leg time, may be ABSENT even when splits exist (mispunch)
  control.cn    control sequence number on the leg
  control.cc    physical control code (stable across legs/forks)
  control.cl    straight-line leg distance to the control, in metres
  control.ct    cumulative time at the control
  control.cd    split time to the control, "-" when missing/skipped
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


def parse_time(text: Optional[str]) -> Optional[int]:
    """Parse "h:mm:ss" or "m:ss" into seconds. None/"-"/"" -> None."""
    if not text or text == "-":
        return None
    parts = text.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        h, m, s = nums
        return h * 3600 + m * 60 + s
    if len(nums) == 2:
        m, s = nums
        return m * 60 + s
    if len(nums) == 1:
        return nums[0]
    return None


def fmt_time(secs: Optional[int]) -> str:
    """Format seconds as "h:mm:ss" or "m:ss". None -> en-dash."""
    if secs is None:
        return "–"
    secs = int(round(secs))
    sign = "-" if secs < 0 else ""
    secs = abs(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{sign}{h}:{m:02d}:{s:02d}"
    return f"{sign}{m}:{s:02d}"


def fmt_gap(secs: Optional[int]) -> str:
    """Format a gap with explicit + sign (0 -> even)."""
    if secs is None:
        return "–"
    if secs == 0:
        return "±0:00"
    return ("+" if secs > 0 else "-") + fmt_time(abs(secs))


def fmt_pace(secs_per_km: Optional[float]) -> str:
    """Format a pace (seconds per km) as "m:ss/km"."""
    if secs_per_km is None:
        return "–"
    return fmt_time(int(round(secs_per_km))) + "/km"


@dataclass
class Split:
    cn: int                       # control sequence number on the leg
    cc: str                       # physical control code
    dist_m: Optional[int]         # straight-line distance to this control (m)
    cum_secs: Optional[int]       # cumulative time at the control
    split_secs: Optional[int]     # split time to the control (None if "-")

    @property
    def pace(self) -> Optional[float]:
        """Seconds per km for this split, if distance and time are known."""
        if self.split_secs and self.dist_m and self.dist_m > 0:
            return self.split_secs / (self.dist_m / 1000.0)
        return None


@dataclass
class Leg:
    legnro: int
    runner: str
    course: str
    emit: str
    leg_secs: Optional[int]       # official leg time; None if no valid result
    splits: list[Split] = field(default_factory=list)

    @property
    def has_result(self) -> bool:
        return self.leg_secs is not None

    @property
    def total_dist_m(self) -> Optional[int]:
        ds = [s.dist_m for s in self.splits if s.dist_m]
        return sum(ds) if ds else None


@dataclass
class Team:
    teamid: str
    teamname: str
    teamnro: str
    placement: Optional[int]
    total_secs: Optional[int]
    legs: list[Leg] = field(default_factory=list)

    @property
    def is_ranked(self) -> bool:
        return self.placement is not None
