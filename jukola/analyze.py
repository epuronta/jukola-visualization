"""Compute deterministic insights from parsed teams.

Two layers:
  Field      — whole-event aggregates (leg rankings, standings per exchange,
               per-segment best splits) computed once.
  TeamInsights / LegInsight / SplitInsight — per-team derived views, plain
               dataclasses that both the HTML renderer and a future LLM
               summarizer can consume.

Notes on method (kept honest so the report can be worded carefully):
  * "Position after leg k" ranks the cumulative sum of leg times of teams that
    have a valid result on every leg 1..k. A mispunch drops a team out of the
    running standings from that leg on. This is the exchange order, not the
    on-course mass-start clock.
  * Split comparison keys on the physical control pair (cc_from -> cc_to), so
    forked runners are only ever compared against others who ran the same
    segment. The segment "best" uses a low percentile rather than the raw
    minimum to resist a single fluke-fast punch.
  * "Time lost" is the summed gap to each segment's best — a rough lower bound
    on mistakes, not an exact figure.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .model import Leg, Split, Team

MISTAKE_MIN_SECS = 25      # ignore losses smaller than this (noise)
MISTAKE_MIN_FRAC = 0.20    # ... and require it to be this fraction of the best
SEGMENT_MIN_SAMPLE = 8     # below this, fall back toward the raw minimum


def _rank(sorted_vals: list[int], value: int) -> int:
    """Competition rank of value within ascending sorted_vals (1-based)."""
    return bisect.bisect_left(sorted_vals, value) + 1


@dataclass
class Field:
    n_legs: int
    leg_times: dict[int, list[int]]                 # legnro -> sorted leg secs
    standings: dict[int, list[int]]                 # k -> sorted cum secs after k legs
    # key is (legnro, cc_from, cc_to): a fork segment is only ever compared
    # within its own leg, matching the official split view.
    segment_times: dict[tuple[int, str, str], list[int]]
    leg_winner: dict[int, tuple[int, str, str]]     # legnro -> (secs, runner, team)
    winner_total: Optional[int]                     # official winning total time (secs)
    # (legnro, cc) -> sorted relay-cumulative times (exchange-before + ct) of
    # every team validly at that control: the live overall standings per control.
    relay_cum_times: dict[tuple[int, str], list[int]]

    def leg_rank(self, legnro: int, secs: int) -> tuple[int, int]:
        vals = self.leg_times.get(legnro, [])
        return _rank(vals, secs), len(vals)

    def position_after(self, k: int, cum_secs: int) -> tuple[int, int]:
        vals = self.standings.get(k, [])
        return _rank(vals, cum_secs), len(vals)

    def segment_best(self, key: tuple[int, str, str]) -> Optional[float]:
        vals = self.segment_times.get(key)
        return _percentile_best(vals) if vals else None

    def segment_rank(self, key: tuple[int, str, str], secs: int) -> tuple[Optional[int], int]:
        """Rank of this split among everyone who ran the same fork segment."""
        vals = self.segment_times.get(key)
        if not vals:
            return None, 0
        return _rank(vals, secs), len(vals)

    def relay_position(self, legnro: int, cc: str, relay_cum: int) -> tuple[Optional[int], int]:
        """Overall relay placing at a control (rank of relay-cumulative time)."""
        vals = self.relay_cum_times.get((legnro, cc))
        if not vals:
            return None, 0
        return _rank(vals, relay_cum), len(vals)


def _percentile_best(times_sorted: list[int]) -> float:
    n = len(times_sorted)
    if n == 0:
        return 0.0
    if n < SEGMENT_MIN_SAMPLE:
        return float(times_sorted[0])
    idx = max(0, int(n * 0.02))
    return float(times_sorted[idx])


def build_field(teams: list[Team]) -> Field:
    n_legs = max((len(t.legs) for t in teams), default=0)
    leg_times: dict[int, list[int]] = defaultdict(list)
    seg_times: dict[tuple[int, str, str], list[int]] = defaultdict(list)
    standings_raw: dict[int, list[int]] = defaultdict(list)
    relay_cum: dict[tuple[int, str], list[int]] = defaultdict(list)
    leg_winner: dict[int, tuple[int, str, str]] = {}

    for t in teams:
        cum = 0
        still_in = True
        for leg in t.legs:
            ex_before = cum             # exchange time entering this leg
            valid_before = still_in     # chain valid up to this leg's start?
            if leg.leg_secs is not None:
                leg_times[leg.legnro].append(leg.leg_secs)
                w = leg_winner.get(leg.legnro)
                if w is None or leg.leg_secs < w[0]:
                    leg_winner[leg.legnro] = (leg.leg_secs, leg.runner, t.teamname)
            # cumulative standings: only while the chain of results is unbroken
            if still_in and leg.leg_secs is not None:
                cum += leg.leg_secs
                standings_raw[leg.legnro].append(cum)
            else:
                still_in = False
            # live overall standings at each control: relay-cumulative time of
            # every team whose chain was valid entering this leg (the runner may
            # still mispunch this leg — they were physically at that position).
            if valid_before:
                for s in leg.splits:
                    if s.cum_secs is not None:
                        relay_cum[(leg.legnro, s.cc)].append(ex_before + s.cum_secs)
            # segment splits, keyed on (leg, physical control pair) — within-leg.
            # Only legs with a valid official result count toward the comparison
            # pool, matching the official split view (a mispunched leg still has
            # punches, but they don't rank others). A runner on a result-less
            # leg is still ranked *against* this pool on their own page.
            if leg.leg_secs is not None:
                prev_cc = "S"
                for s in leg.splits:
                    if s.split_secs is not None:
                        seg_times[(leg.legnro, prev_cc, s.cc)].append(s.split_secs)
                    prev_cc = s.cc

    for v in leg_times.values():
        v.sort()
    for v in standings_raw.values():
        v.sort()
    for v in seg_times.values():
        v.sort()
    for v in relay_cum.values():
        v.sort()
    totals = [t.total_secs for t in teams if t.total_secs is not None]
    return Field(
        n_legs=n_legs,
        leg_times=dict(leg_times),
        standings=dict(standings_raw),
        segment_times=dict(seg_times),
        leg_winner=leg_winner,
        winner_total=min(totals) if totals else None,
        relay_cum_times=dict(relay_cum),
    )


@dataclass
class SplitInsight:
    cn: int
    cc: str
    from_cc: str                  # previous control code ("S" = start); the leg is from_cc -> cc
    cum_secs: Optional[int]       # cumulative time at this control (for time-spaced x-axis)
    split_secs: Optional[int]
    dist_m: Optional[int]
    pace: Optional[float]
    best_secs: Optional[float]
    time_loss: Optional[int]      # secs behind segment best (>=0), None if unknown
    is_mistake: bool
    missing: bool                 # control skipped / no split recorded
    rank: Optional[int] = None    # rank on this fork segment (1 = fastest)
    field_size: int = 0           # how many ran this exact segment
    pct: Optional[float] = None   # rank as fraction 0..1 (0 = fastest), for plotting
    relay_pos: Optional[int] = None  # overall relay placing at this control
    relay_field: int = 0          # teams validly at this control


@dataclass
class LegInsight:
    legnro: int
    runner: str
    course: str
    leg_secs: Optional[int]
    has_result: bool
    leg_rank: Optional[int]
    leg_field: Optional[int]
    gap_to_best: Optional[int]
    position: Optional[int]       # team position after this leg
    position_field: Optional[int]
    position_delta: Optional[int]  # places gained (+) or lost (-) vs prev leg
    total_dist_m: Optional[int]
    avg_pace: Optional[float]
    time_lost: int                # summed gap to segment bests
    start_position: Optional[int] = None  # position entering the leg (leg 1: grid = team number)
    splits: list[SplitInsight] = field(default_factory=list)
    worst_splits: list[SplitInsight] = field(default_factory=list)
    note: str = ""


@dataclass
class TeamInsights:
    teamid: str
    teamname: str
    teamnro: str
    placement: Optional[int]
    total_secs: Optional[int]
    gap_to_winner: Optional[int]
    status: str                   # "ranked" | "unranked"
    legs: list[LegInsight]
    position_curve: list[tuple[int, Optional[int]]]
    best_leg: Optional[LegInsight]
    worst_leg: Optional[LegInsight]
    biggest_gain: Optional[LegInsight]
    biggest_drop: Optional[LegInsight]
    total_time_lost: int


def _analyze_splits(leg: Leg, field_: Field,
                    exchange_before: Optional[int]) -> tuple[list[SplitInsight], int]:
    out: list[SplitInsight] = []
    total_lost = 0
    prev_cc = "S"
    for s in leg.splits:
        from_cc = prev_cc
        key = (leg.legnro, prev_cc, s.cc)
        best = field_.segment_best(key)
        prev_cc = s.cc
        # overall relay placing at this control (defined whenever the team had a
        # valid chain into this leg and reached the control)
        relay_pos = None
        relay_field = 0
        if exchange_before is not None and s.cum_secs is not None:
            relay_pos, relay_field = field_.relay_position(
                leg.legnro, s.cc, exchange_before + s.cum_secs)
        if s.split_secs is None:
            out.append(SplitInsight(s.cn, s.cc, from_cc, s.cum_secs, None, s.dist_m,
                                    None, best, None, False, missing=True,
                                    relay_pos=relay_pos, relay_field=relay_field))
            continue
        rank, fsize = field_.segment_rank(key, s.split_secs)
        pct = (rank - 1) / (fsize - 1) if rank and fsize > 1 else (0.0 if rank else None)
        time_loss = None
        is_mistake = False
        if best is not None:
            time_loss = max(0, int(round(s.split_secs - best)))
            total_lost += time_loss
            is_mistake = (
                time_loss >= MISTAKE_MIN_SECS
                and time_loss >= MISTAKE_MIN_FRAC * best
            )
        out.append(SplitInsight(s.cn, s.cc, from_cc, s.cum_secs, s.split_secs, s.dist_m,
                                s.pace, best, time_loss, is_mistake, missing=False,
                                rank=rank, field_size=fsize, pct=pct,
                                relay_pos=relay_pos, relay_field=relay_field))
    return out, total_lost


def analyze_team(team: Team, field_: Field) -> TeamInsights:
    legs_out: list[LegInsight] = []
    cum = 0
    still_in = True
    prev_position: Optional[int] = None
    total_time_lost = 0
    # team number = mass-start grid position (the bib); the field's start anchor
    team_number = int(team.teamid) if team.teamid.isdigit() else None

    for leg in team.legs:
        exchange_before = cum if still_in else None
        # position entering this leg: grid (team number) on leg 1, otherwise the
        # exchange standing carried over from the previous leg
        start_position = team_number if leg.legnro == 1 else (
            prev_position if still_in else None)
        splits, time_lost = _analyze_splits(leg, field_, exchange_before)
        total_time_lost += time_lost
        worst = sorted(
            (s for s in splits if s.time_loss),
            key=lambda s: s.time_loss or 0, reverse=True,
        )[:3]

        leg_rank = leg_field = gap_to_best = None
        if leg.has_result:
            leg_rank, leg_field = field_.leg_rank(leg.legnro, leg.leg_secs)
            best = field_.leg_winner.get(leg.legnro)
            gap_to_best = leg.leg_secs - best[0] if best else None

        position = position_field = position_delta = None
        if still_in and leg.has_result:
            cum += leg.leg_secs
            position, position_field = field_.position_after(leg.legnro, cum)
            if prev_position is not None:
                position_delta = prev_position - position
            prev_position = position
        else:
            still_in = False

        note = ""
        if not leg.has_result:
            note = "no official result (mispunch / DNF)" if leg.splits else "did not start"

        legs_out.append(LegInsight(
            legnro=leg.legnro, runner=leg.runner, course=leg.course,
            leg_secs=leg.leg_secs, has_result=leg.has_result,
            leg_rank=leg_rank, leg_field=leg_field, gap_to_best=gap_to_best,
            position=position, position_field=position_field,
            position_delta=position_delta,
            total_dist_m=leg.total_dist_m,
            avg_pace=(leg.leg_secs / (leg.total_dist_m / 1000.0)
                      if leg.has_result and leg.total_dist_m else None),
            time_lost=time_lost, start_position=start_position,
            splits=splits, worst_splits=worst, note=note,
        ))

    ranked = [l for l in legs_out if l.has_result and l.leg_rank]
    best_leg = min(ranked, key=lambda l: l.leg_rank) if ranked else None
    worst_leg = max(ranked, key=lambda l: l.leg_rank) if ranked else None
    moved = [l for l in legs_out if l.position_delta is not None]
    biggest_gain = max(moved, key=lambda l: l.position_delta) if moved else None
    biggest_drop = min(moved, key=lambda l: l.position_delta) if moved else None

    gap_to_winner = None
    if team.total_secs is not None and field_.winner_total is not None:
        gap_to_winner = team.total_secs - field_.winner_total

    return TeamInsights(
        teamid=team.teamid, teamname=team.teamname, teamnro=team.teamnro,
        placement=team.placement, total_secs=team.total_secs,
        gap_to_winner=gap_to_winner,
        status="ranked" if team.is_ranked else "unranked",
        legs=legs_out,
        position_curve=[(l.legnro, l.position) for l in legs_out],
        best_leg=best_leg, worst_leg=worst_leg,
        biggest_gain=biggest_gain if biggest_gain and biggest_gain.position_delta > 0 else None,
        biggest_drop=biggest_drop if biggest_drop and biggest_drop.position_delta < 0 else None,
        total_time_lost=total_time_lost,
    )
