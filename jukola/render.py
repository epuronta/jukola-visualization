"""Render team insights to self-contained static HTML.

The signature visual is one split-rank line chart per leg: for each control,
the runner's rank among everyone who ran that exact fork segment. The line is
positioned by percentile (0 = fastest, comparable across forks of different
field sizes) and every point is labelled with the literal rank/field.
"""

from __future__ import annotations

from html import escape
from typing import Optional

from .analyze import LegInsight, SplitInsight, TeamInsights
from .model import fmt_gap, fmt_pace, fmt_time

# chart geometry
_W, _H = 880, 240
_L, _R, _T, _B = 46, 16, 18, 40
_PW, _PH = _W - _L - _R, _H - _T - _B

# colours
_C_POINT = "#3b7dd8"      # all split points (height carries performance)
_C_MISS = "#e4572e"       # skipped / mispunch marker (a data state, not a tier)
_C_GRID = "#e6e6e6"
_C_AXIS = "#9aa0a6"


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _x(i: int, n: int) -> float:
    if n <= 1:
        return _L + _PW / 2
    return _L + _PW * i / (n - 1)


def _y(pct: float) -> float:
    return _T + _PH * pct


def _time_step(total: int) -> int:
    """Pick a 'nice' x-axis tick interval (secs) giving ~4-6 gridlines."""
    for st in (120, 300, 600, 900, 1200, 1800, 3600, 7200):
        if total / st <= 6:
            return st
    return 7200


def split_rank_chart(leg: LegInsight) -> str:
    """Inline SVG: split-rank progression across one leg's controls.

    The x-axis is cumulative time from start to finish, so each segment's
    horizontal width is its split duration. A short split that cost rank stays
    visually small; a long time-sink dominates the chart — conveying how much
    each split actually mattered. Controls the fork skipped are simply absent
    from the timeline (the time gap shows them); fork junctions are marked.
    """
    pts = [s for s in leg.splits if s.cn and s.cum_secs is not None]
    if not pts:
        return '<p class="muted">No split data for this leg.</p>'

    total = max(s.cum_secs for s in pts)

    def x(t: int) -> float:
        return _L + _PW * t / total if total else _L + _PW / 2

    parts: list[str] = [
        f'<svg viewBox="0 0 {_W} {_H}" class="chart" role="img" '
        f'aria-label="Split rank progression for leg {leg.legnro}">'
    ]

    # vertical time gridlines + bottom labels
    step = _time_step(total)
    t = 0
    while t <= total:
        gx = x(t)
        parts.append(f'<line x1="{gx:.1f}" y1="{_T}" x2="{gx:.1f}" '
                     f'y2="{_T + _PH}" stroke="{_C_GRID}"/>')
        parts.append(f'<text x="{gx:.1f}" y="{_H - _B + 14}" text-anchor="middle" '
                     f'class="xtick">{fmt_time(t)}</text>')
        t += step

    # horizontal gridlines + y labels (percentile: top = fastest)
    for frac, label in [(0.0, "fastest"), (0.25, "25%"), (0.5, "50%"),
                        (0.75, "75%"), (1.0, "slowest")]:
        y = _y(frac)
        parts.append(
            f'<line x1="{_L}" y1="{y:.1f}" x2="{_W - _R}" y2="{y:.1f}" '
            f'stroke="{_C_GRID}"/>'
        )
        parts.append(
            f'<text x="{_L - 6}" y="{y + 3:.1f}" text-anchor="end" '
            f'class="tick">{label}</text>'
        )

    def plottable(s) -> bool:
        return s is not None and not s.missing and s.pct is not None

    # fork-junction markers (control reached, but split spans a fork and isn't
    # comparable) — a faint dashed vertical at the time it was reached.
    for s in pts:
        if plottable(s):
            continue
        gx = x(s.cum_secs)
        parts.append(
            f'<g><line x1="{gx:.1f}" y1="{_T}" x2="{gx:.1f}" y2="{_T + _PH}" '
            f'stroke="{_C_MISS}" stroke-width="1" stroke-dasharray="2 3" '
            f'opacity="0.6"/><title>Control {escape(s.cc)}: fork junction — '
            f'split not comparable</title></g>'
        )

    # line: connect plottable points; break across fork gaps / skipped controls
    run: list[tuple[float, float]] = []
    prev_cn = None

    def flush() -> None:
        if len(run) >= 2:
            d = " ".join(f"{px:.1f},{py:.1f}" for px, py in run)
            parts.append(f'<polyline points="{d}" fill="none" '
                         f'stroke="#b9c4d4" stroke-width="2"/>')

    for s in pts:
        gap = prev_cn is not None and s.cn != prev_cn + 1
        if not plottable(s) or gap:
            flush()
            run = []
        if plottable(s):
            run.append((x(s.cum_secs), _y(s.pct)))
        prev_cn = s.cn
    flush()

    # points + decluttered control-number labels
    last_label_x = -1e9
    for s in pts:
        if not plottable(s):
            continue
        px, py = x(s.cum_secs), _y(s.pct)
        rank_txt = f"{_ordinal(s.rank)} of {s.field_size}" if s.rank else "–"
        loss = f"  (+{fmt_time(s.time_loss)})" if s.time_loss else ""
        tip = (f"Control {s.cn} ({escape(s.cc)}) — {fmt_time(s.split_secs)} — "
               f"{rank_txt} — {fmt_pace(s.pace)}{loss}")
        parts.append(
            f'<g><circle cx="{px:.1f}" cy="{py:.1f}" r="4" '
            f'fill="{_C_POINT}"/><title>{tip}</title></g>'
        )
        if px - last_label_x >= 20:
            parts.append(
                f'<text x="{px:.1f}" y="{py - 9:.1f}" text-anchor="middle" '
                f'class="cnum">{s.cn}</text>'
            )
            last_label_x = px

    parts.append(
        f'<text x="{_L}" y="{_H - 6}" class="axis-title">time →</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _leg_block(leg: LegInsight) -> str:
    runner = escape(leg.runner) or "—"
    course = escape(leg.course)
    if leg.has_result:
        meta = (f'{fmt_time(leg.leg_secs)} · leg {leg.leg_rank}/{leg.leg_field}'
                f' · +{fmt_time(leg.gap_to_best)} to leg winner')
    elif leg.splits:
        meta = '<span class="warn">no official result (mispunch / DNF)</span>'
    else:
        meta = '<span class="warn">did not start</span>'

    stat_bits = []
    if leg.total_dist_m:
        stat_bits.append(f"{leg.total_dist_m/1000:.1f} km")
    if leg.avg_pace:
        stat_bits.append(fmt_pace(leg.avg_pace))
    if leg.position is not None:
        delta = ""
        if leg.position_delta:
            cls = "up" if leg.position_delta > 0 else "down"
            arrow = "▲" if leg.position_delta > 0 else "▼"
            delta = f' <span class="{cls}">{arrow}{abs(leg.position_delta)}</span>'
        stat_bits.append(f"position {leg.position}{delta}")
    if leg.time_lost:
        stat_bits.append(f"~{fmt_time(leg.time_lost)} lost vs fork bests")
    stats = " · ".join(stat_bits)

    chart = split_rank_chart(leg)

    worst = ""
    flagged = [s for s in leg.worst_splits if s.is_mistake]
    if flagged:
        def _loss_item(s) -> str:
            # identify the segment by control NUMBER (matches the chart x-axis),
            # since a ranked split is always between consecutive controls; show
            # the control codes secondarily for cross-referencing.
            frm = "start" if s.from_cc == "S" else str(s.cn - 1)
            codes = f"{escape('S' if s.from_cc == 'S' else s.from_cc)}&rarr;{escape(s.cc)}"
            return (
                f"<li>Control <b>{frm}&rarr;{s.cn}</b> "
                f'<span class="muted">({codes})</span>: {fmt_time(s.split_secs)} '
                f"({_ordinal(s.rank)} of {s.field_size}), +{fmt_time(s.time_loss)}</li>"
            )
        items = "".join(_loss_item(s) for s in flagged if s.rank)
        worst = f'<div class="mistakes"><b>Biggest time losses</b><ul>{items}</ul></div>'

    return (
        f'<section class="leg">'
        f'<div class="leg-head"><h3>Leg {leg.legnro} · {runner}'
        f'<span class="course">{course}</span></h3>'
        f'<div class="leg-meta">{meta}</div></div>'
        f'<div class="leg-stats">{stats}</div>'
        f'{chart}{worst}'
        f'</section>'
    )


def render_team_page(t: TeamInsights, event_name: str) -> str:
    title = escape(t.teamname)
    if t.status == "ranked":
        head_stat = (f'<span class="place">{t.placement}.</span> '
                     f'{fmt_time(t.total_secs)} '
                     f'<span class="muted">({fmt_gap(t.gap_to_winner)} to winner)</span>')
    else:
        ran = sum(1 for l in t.legs if l.has_result)
        head_stat = (f'<span class="dnf">unranked</span> '
                     f'<span class="muted">— {ran} of {len(t.legs)} legs completed</span>')

    legs_html = "".join(_leg_block(l) for l in t.legs)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — {escape(event_name)}</title>
<style>{_CSS}</style></head>
<body>
<header class="page-head">
  <div class="crumb"><a href="index.html">← all teams</a> · {escape(event_name)}</div>
  <h1>{title} <span class="bib">#{escape(t.teamnro)}</span></h1>
  <div class="result">{head_stat}</div>
  <p class="legend">
    <span class="dot point"></span> control split (height = rank on that fork)
    <span class="fork-key"></span> fork junction / skipped control (no comparable split)
  </p>
</header>
<main>{legs_html}</main>
<footer>Each chart ranks every control split against the runners who ran that
exact fork segment. Line position is percentile (top = fastest); hover a point
for the literal rank.</footer>
</body></html>"""


_CSS = """
:root { --fg:#1a1d21; --muted:#6b7280; --line:#e6e6e6; --accent:#3b7dd8; }
* { box-sizing: border-box; }
body { font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: var(--fg); margin: 0; background: #fafbfc; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.page-head { padding: 24px max(16px, 5vw); border-bottom: 1px solid var(--line);
  background: #fff; }
.crumb { color: var(--muted); font-size: 13px; }
h1 { margin: 8px 0 4px; font-size: 26px; }
.bib { color: var(--muted); font-weight: 400; font-size: 18px; }
.result { font-size: 18px; }
.place { font-weight: 700; color: var(--accent); }
.dnf { color: #e4572e; font-weight: 600; }
.muted { color: var(--muted); }
.legend { font-size: 13px; color: var(--muted); margin: 12px 0 0; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  margin: 0 3px 0 10px; vertical-align: middle; }
.dot.point { background: #3b7dd8; }
.fork-key { display: inline-block; width: 12px; height: 0; margin: 0 4px 0 10px;
  border-top: 1.5px dashed #e4572e; vertical-align: middle; }
main { padding: 8px max(16px, 5vw) 40px; }
.leg { background: #fff; border: 1px solid var(--line); border-radius: 10px;
  padding: 16px 18px; margin: 16px 0; }
.leg-head { display: flex; justify-content: space-between; align-items: baseline;
  flex-wrap: wrap; gap: 4px 16px; }
.leg-head h3 { margin: 0; font-size: 18px; }
.course { color: var(--muted); font-weight: 400; font-size: 13px; margin-left: 8px; }
.leg-meta { color: var(--fg); font-size: 14px; }
.warn { color: #e4572e; }
.leg-stats { color: var(--muted); font-size: 13px; margin: 2px 0 8px; }
.up { color: #1a9850; } .down { color: #e4572e; }
.chart { width: 100%; height: auto; display: block; }
.tick { fill: #9aa0a6; font-size: 11px; }
.xtick { fill: #b0b6bd; font-size: 9px; }
.cnum { fill: #8a93a0; font-size: 9px; }
.axis-title { fill: #9aa0a6; font-size: 11px; }
.chart circle:hover { stroke: #1a1d21; stroke-width: 1.5; }
.mistakes { font-size: 13px; background: #fff6f3; border: 1px solid #f6d9cf;
  border-radius: 8px; padding: 8px 12px; margin-top: 10px; }
.mistakes ul { margin: 4px 0 0; padding-left: 18px; }
footer { color: var(--muted); font-size: 12px; padding: 0 max(16px,5vw) 40px;
  max-width: 70ch; }
"""
