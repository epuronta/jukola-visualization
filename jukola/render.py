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

# chart geometry (extra right margin for the position axis labels)
_W, _H = 880, 240
_L, _R, _T, _B = 46, 48, 18, 40
_PW, _PH = _W - _L - _R, _H - _T - _B

# colours
_C_POINT = "#3b7dd8"      # split points (height = rank on that fork)
_C_MISS = "#e4572e"       # fork-junction / skipped-control marker
_C_POS = "#1a9850"        # overall relay-position series (right axis, green squares)
_C_GRID = "#e6e6e6"


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _y(pct: float) -> float:
    return _T + _PH * pct


def _dist_step(total: float) -> int:
    """Pick a 'nice' distance tick interval (m) giving ~4-6 gridlines."""
    for st in (250, 500, 1000, 2000, 2500, 5000, 10000):
        if total / st <= 6:
            return st
    return 10000


def split_rank_chart(leg: LegInsight) -> str:
    """Inline SVG: split-rank progression across one leg's controls.

    The x-axis is cumulative straight-line distance (cl), so each segment's
    horizontal width is the ground it covers. A short leg that cost rank shows
    as a narrow, deep spike (clearly a nav error); long legs get proportional
    width. Controls the fork skipped are absent from the axis (their distance
    isn't in the runner's data, so the distance slightly undercounts at fork
    junctions); fork junctions are marked.
    """
    pts = [s for s in leg.splits if s.cn and s.cum_secs is not None]
    if not pts:
        return '<p class="muted">No split data for this leg.</p>'

    xv: dict[int, float] = {}
    cum = 0.0
    for s in pts:
        cum += s.dist_m or 0
        xv[s.cn] = cum
    total = cum or 1.0
    step = _dist_step(total)

    def x(cn: int) -> float:
        return _L + _PW * xv[cn] / total

    parts: list[str] = [
        f'<svg viewBox="0 0 {_W} {_H}" class="chart" role="img" '
        f'aria-label="Split rank progression for leg {leg.legnro}">'
    ]

    # vertical gridlines + bottom labels (time or distance)
    t = 0.0
    while t <= total:
        gx = _L + _PW * t / total
        parts.append(f'<line x1="{gx:.1f}" y1="{_T}" x2="{gx:.1f}" '
                     f'y2="{_T + _PH}" stroke="{_C_GRID}"/>')
        parts.append(f'<text x="{gx:.1f}" y="{_H - _B + 14}" text-anchor="middle" '
                     f'class="xtick">{t / 1000:g} km</text>')
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
        gx = x(s.cn)
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
            run.append((x(s.cn), _y(s.pct)))
        prev_cn = s.cn
    flush()

    # points + decluttered control-number labels
    last_label_x = -1e9
    for s in pts:
        if not plottable(s):
            continue
        px, py = x(s.cn), _y(s.pct)
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

    parts.append(_position_series(leg, pts, x))

    parts.append(
        f'<text x="{_L}" y="{_H - 6}" class="axis-title">distance →</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _position_series(leg: LegInsight, pts: list, x) -> str:
    """Overall relay position on a right axis. Anchored at the start (distance 0)
    — grid position (= team number) on leg 1, the exchange standing otherwise —
    then plotted at common (full-field) controls only. At forked controls the
    'position' is just a placing within that fork, not a true standing."""
    have = [s for s in pts if s.relay_pos and s.relay_field]
    commons = []
    if have:
        leg_max = max(s.relay_field for s in have)
        commons = [s for s in have if s.relay_field >= 0.75 * leg_max]
    last_cn = max((s.cn for s in pts), default=0)
    # the leg's finish IS the exchange; prefer the canonical exchange standing
    # (leg.position, = the official change-over placing) over the per-control
    # pool there, so the endpoint matches the header and the next leg's start.
    use_exchange = leg.position is not None

    # nodes: (x, position, tooltip). Start anchor, intermediate commons, exchange.
    nodes: list[tuple[float, int, str]] = []
    if leg.start_position is not None:
        where = "grid start" if leg.legnro == 1 else "at exchange"
        nodes.append((float(_L), leg.start_position,
                      f"Start ({where}): position {leg.start_position}"))
    for s in commons:
        if use_exchange and s.cn == last_cn:
            continue  # replaced by the canonical exchange node below
        nodes.append((x(s.cn), s.relay_pos,
                      f"After control {s.cn}: {_ordinal(s.relay_pos)} overall "
                      f"(of {s.relay_field})"))
    if use_exchange and last_cn:
        field_txt = f" (of {leg.position_field})" if leg.position_field else ""
        nodes.append((x(last_cn), leg.position,
                      f"At exchange: {_ordinal(leg.position)} overall{field_txt}"))
    if len(nodes) < 2:
        return ""

    positions = [p for _, p, _ in nodes]
    pmin, pmax = min(positions), max(positions)
    # best position reached sits on the top line; pad only the bottom
    hi = pmax + max(1.0, (pmax - pmin) * 0.15)
    lo = pmin

    def yp(pos: int) -> float:
        return _T + _PH * (pos - lo) / (hi - lo)  # smaller (better) -> top

    out: list[str] = []
    pl = " ".join(f"{nx:.1f},{yp(p):.1f}" for nx, p, _ in nodes)
    out.append(f'<polyline points="{pl}" fill="none" stroke="{_C_POS}" '
               f'stroke-width="1.5" opacity="0.85"/>')
    for nx, p, tip in nodes:
        out.append(
            f'<g><rect x="{nx - 3.5:.1f}" y="{yp(p) - 3.5:.1f}" width="7" height="7" '
            f'fill="{_C_POS}"/><title>{escape(tip)}</title></g>'
        )
    # right-axis labels: best (top) and worst (bottom) position reached
    rx = _W - _R + 5
    out.append(f'<text x="{rx}" y="{yp(pmin) + 3:.1f}" class="postick">{pmin}</text>')
    out.append(f'<text x="{rx}" y="{yp(pmax) + 3:.1f}" class="postick">{pmax}</text>')
    out.append(f'<text x="{_W - 2}" y="{_T - 6}" text-anchor="end" '
               f'class="postick">position</text>')
    return "".join(out)


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


# whole-race overview geometry (wider; extra top room for runner names)
_OW, _OH = 1200, 300
_OL, _ORR, _OT, _OB = 46, 50, 40, 40
_OPW, _OPH = _OW - _OL - _ORR, _OH - _OT - _OB


def _trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: max(1, n - 1)] + "…"


def _leg_dist_cumsum(leg) -> dict[int, float]:
    """Within-leg cumulative distance (m) keyed by control number."""
    out: dict[int, float] = {}
    cum = 0.0
    for s in leg.splits:
        if s.cn and s.cum_secs is not None:
            cum += s.dist_m or 0
            out[s.cn] = cum
    return out


def overview_chart(t: TeamInsights) -> str:
    """A single graph spanning the whole relay: split-rank texture per leg plus
    the continuous overall-position line, with the x-axis scaled by cumulative
    distance so each leg is as wide as it is long. Dividers + runner names mark
    the exchanges."""
    legs = t.legs
    dists = [(l.total_dist_m or 0) for l in legs]
    bnd = [0.0]
    for d in dists:
        bnd.append(bnd[-1] + d)
    total = bnd[-1] or 1.0
    if total <= 1:
        return ""

    def gx(d: float) -> float:
        return _OL + _OPW * d / total

    def gy(pct: float) -> float:
        return _OT + _OPH * pct

    p: list[str] = [
        f'<svg viewBox="0 0 {_OW} {_OH}" class="chart" role="img" '
        f'aria-label="Whole-race overview for {escape(t.teamname)}">'
    ]

    # horizontal gridlines + left (percentile) labels
    for frac, label in [(0.0, "fastest"), (0.5, "50%"), (1.0, "slowest")]:
        y = gy(frac)
        p.append(f'<line x1="{_OL}" y1="{y:.1f}" x2="{_OW - _ORR}" y2="{y:.1f}" '
                 f'stroke="{_C_GRID}"/>')
        p.append(f'<text x="{_OL - 6}" y="{y + 3:.1f}" text-anchor="end" '
                 f'class="tick">{label}</text>')

    # leg dividers, runner names (top), cumulative-distance labels (bottom)
    for i, leg in enumerate(legs):
        x0, x1 = gx(bnd[i]), gx(bnd[i + 1])
        if dists[i] <= 0:
            continue
        if i > 0:
            p.append(f'<line x1="{x0:.1f}" y1="{_OT}" x2="{x0:.1f}" '
                     f'y2="{_OT + _OPH}" stroke="#cfd4da"/>')
        cx = (x0 + x1) / 2
        name = _trunc(f"L{leg.legnro} {leg.runner}", int((x1 - x0) / 5.5))
        p.append(f'<text x="{cx:.1f}" y="{_OT - 24:.1f}" text-anchor="middle" '
                 f'class="legname">{escape(name)}</text>')
        p.append(f'<text x="{x1:.1f}" y="{_OH - _OB + 14:.1f}" text-anchor="middle" '
                 f'class="xtick">{bnd[i + 1] / 1000:g} km</text>')

    # split-rank texture: a thin line per leg (break across forks)
    for i, leg in enumerate(legs):
        xv = _leg_dist_cumsum(leg)
        run: list[tuple[float, float]] = []
        prev_cn = None

        def flush(run=run):
            if len(run) >= 2:
                d = " ".join(f"{a:.1f},{b:.1f}" for a, b in run)
                p.append(f'<polyline points="{d}" fill="none" stroke="#c7d2e2" '
                         f'stroke-width="1.5"/>')
        for s in leg.splits:
            ok = s.cn in xv and not s.missing and s.pct is not None
            gap = prev_cn is not None and s.cn != prev_cn + 1
            if not ok or gap:
                flush(); run = run[:0]
            if ok:
                run.append((gx(bnd[i] + xv[s.cn]), gy(s.pct)))
            prev_cn = s.cn
        flush()

    # continuous overall-position line (right axis), across the whole relay
    nodes: list[tuple[float, int, str]] = []
    if legs and legs[0].start_position is not None:
        nodes.append((gx(0), legs[0].start_position,
                      f"Start (grid): position {legs[0].start_position}"))
    for i, leg in enumerate(legs):
        xv = _leg_dist_cumsum(leg)
        have = [s for s in leg.splits if s.relay_pos and s.relay_field and s.cn in xv]
        commons = []
        if have:
            lm = max(s.relay_field for s in have)
            commons = [s for s in have if s.relay_field >= 0.75 * lm]
        last_cn = max((s.cn for s in leg.splits if s.cn in xv), default=0)
        use_exchange = leg.position is not None
        for s in commons:
            if use_exchange and s.cn == last_cn:
                continue
            nodes.append((gx(bnd[i] + xv[s.cn]), s.relay_pos,
                          f"L{leg.legnro} after control {s.cn}: "
                          f"{_ordinal(s.relay_pos)} overall"))
        if use_exchange:
            nodes.append((gx(bnd[i + 1]), leg.position,
                          f"After leg {leg.legnro}: {_ordinal(leg.position)} overall"))

    if len(nodes) >= 2:
        positions = [n[1] for n in nodes]
        pmin, pmax = min(positions), max(positions)
        # best position reached sits on the top line; pad only the bottom
        hi = pmax + max(1.0, (pmax - pmin) * 0.15)
        lo = pmin

        def yp(pos: int) -> float:
            return _OT + _OPH * (pos - lo) / (hi - lo)

        pl = " ".join(f"{nx:.1f},{yp(pv):.1f}" for nx, pv, _ in nodes)
        p.append(f'<polyline points="{pl}" fill="none" stroke="{_C_POS}" '
                 f'stroke-width="1.5" opacity="0.9"/>')
        for nx, pv, tip in nodes:
            p.append(f'<g><rect x="{nx - 3:.1f}" y="{yp(pv) - 3:.1f}" width="6" '
                     f'height="6" fill="{_C_POS}"/><title>{escape(tip)}</title></g>')
        rx = _OW - _ORR + 5
        p.append(f'<text x="{rx}" y="{yp(pmin) + 3:.1f}" class="postick">{pmin}</text>')
        p.append(f'<text x="{rx}" y="{yp(pmax) + 3:.1f}" class="postick">{pmax}</text>')
        p.append(f'<text x="{_OW - 2}" y="{_OT - 6}" text-anchor="end" '
                 f'class="postick">position</text>')

    p.append(f'<text x="{_OL}" y="{_OH - 6}" class="axis-title">distance →</text>')
    p.append("</svg>")
    return "".join(p)


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
    overview = (f'<section class="leg overview"><h3>Whole race</h3>'
                f'{overview_chart(t)}</section>')

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
    <span class="dot pos"></span> overall position (right axis, common controls)
    <span class="fork-key"></span> fork junction / skipped control
  </p>
</header>
<main>{overview}{legs_html}</main>
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
.dot.pos { background: #1a9850; border-radius: 1px; }
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
.postick { fill: #1a9850; font-size: 9px; }
.legname { fill: #444b54; font-size: 11px; font-weight: 600; }
.axis-title { fill: #9aa0a6; font-size: 11px; }
.chart circle:hover { stroke: #1a1d21; stroke-width: 1.5; }
.mistakes { font-size: 13px; background: #fff6f3; border: 1px solid #f6d9cf;
  border-radius: 8px; padding: 8px 12px; margin-top: 10px; }
.mistakes ul { margin: 4px 0 0; padding-left: 18px; }
footer { color: var(--muted); font-size: 12px; padding: 0 max(16px,5vw) 40px;
  max-width: 70ch; }
"""
