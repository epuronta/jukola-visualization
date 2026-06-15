# Dataset reference — `results_j2026_ju.xml`

Everything needed to work with the source data without re-studying it. All
numbers below are verified against the actual file (Kotka-Jukola 2026).

> The XML is git-ignored (`results_*.xml`) — it's ~28 MB of participant split
> data and the repo is public. It must be present in the repo root to run the
> generator.

## What it is

Results + full split times for **Jukolan Viesti** (the main men's 7-leg
night relay) at **Kotka-Jukola 2026**. One single class, `JU`. It's an
IOF-relay-style XML export (the same shape Jukola's official split-time pages
render from).

| Quantity | Value |
|---|---|
| Teams | 1876 |
| — ranked (have `placement`) | 1579 |
| — unranked (DNF/DSQ, no `placement`) | 297 |
| Legs per team | 7 (always; `13132` leg elements total) |
| Legs with an official `result` | 11984 |
| Legs without result | 1148 (of which **871 still have split data** — mispunch/DSQ — and 277 are DNS) |
| Control split elements | 302536 |
| Distinct course codes (`crs`) | 118 (forking — see below) |
| Control numbers (`cn`) | 1–32 |
| Controls per leg | 0–32, median 23 |
| Leg distances to a control (`cl`) | 101–2263 m |
| Encoding | UTF-8; times as `h:mm:ss` or `m:ss` |

## Structure

```
event (Type="Relay")
├─ eventname                 "Kotka-Jukola 2026, Jukolan Viesti"
└─ class
   ├─ classname             "JU"
   └─ team  (× 1876)
      ├─ teamid             UNIQUE id — use as the key
      ├─ teamname
      ├─ teamnro            start-group / bib number — NOT unique (20 values)
      ├─ result             final time "h:mm:ss"   (ranked teams only)
      ├─ tsecs              final time in seconds   (ranked teams only)
      ├─ placement          final placing           (ranked teams only)
      └─ leg  (× 7)
         ├─ legnro          1..7
         ├─ nm              runner name
         ├─ crs             course / fork code, e.g. "J316" (forking)
         ├─ emit            EMIT chip number (absent on ~248 legs, mostly DNS)
         ├─ control  (×N)   the splits, in running order
         │  ├─ cn           control SEQUENCE number on the master course
         │  ├─ cc           physical control CODE (stable across legs/forks)
         │  ├─ cl           straight-line leg distance TO this control, metres
         │  ├─ ct           cumulative time at the control ("h:mm:ss"/"m:ss")
         │  └─ cd           split time to the control; "-" at fork boundaries
         ├─ result          leg time (may be ABSENT even with splits present)
         └─ tsecs           leg time in seconds (absent when result is)
```

### Minimal example (one team, trimmed)

```xml
<team>
  <teamid>1</teamid><teamname>Stora Tuna OK</teamname><teamnro>1</teamnro>
  <result>7:52:43</result><tsecs>28363</tsecs><placement>1</placement>
  <leg>
    <legnro>1</legnro><nm>Olle Kalered</nm><crs>J105</crs><emit>1521779</emit>
    <control><cn>1</cn><cc>77</cc><cl>1981</cl><ct>11:48</ct><cd>11:48</cd></control>
    <control><cn>2</cn><cc>186</cc><cl>610</cl><ct>17:04</ct><cd>5:16</cd></control>
    ...
    <result>1:21:39</result><tsecs>4899</tsecs>
  </leg>
  ...
</team>
```

## Field semantics & gotchas

- **`teamid` is the only unique team key.** `teamnro` repeats (only 20 distinct
  values — it's the bib/start batch). Filenames/keys must use `teamid`.
- **`cl` is distance in metres** (straight-line, to that control). Verified:
  `cd / (cl/1000)` gives realistic 5–11 min/km paces. Sum over a leg ≈ leg
  length (legs run ~7–16 km, ~80 km total). Note: a fork-skipped control's `cl`
  is *not* present in a runner's controls, so summing `cl` slightly undercounts
  the official leg distance at fork skips.
- **`ct` (cumulative) is the reliable timing field.** Present on **all** 302536
  controls; only 5 are non-monotonic (data glitches). Derive a split as
  `ct[i] - ct[i-1]` (first control's split = its `ct`).
- **`cd` is `"-"` exactly at forking boundaries** — verified 579/579 cases
  coincide with a gap in `cn` (the master numbering skips a control the runner's
  fork didn't visit), and **all 579 still have a valid `ct`**. `cd` is never a
  mispunch signal; mispunches show up at the leg level (missing `result`).
- **`result`/`tsecs` can be absent on a leg that still has full splits.** That's
  a mispunched/DSQ leg — the runner punched controls (so splits exist) but the
  leg has no official time. 871 such legs. Treat them as "ran, but unranked".
- **Unranked teams** (no `placement`/`result`) are those with a broken result
  chain. They still have rich per-leg split data up to/through the failure.

## Forking — the key concept

Jukola uses **forking**: runners on the same leg run different variants
(`crs` codes; `J` + leg digit + variant, e.g. `J3xx` = leg 3). The `cn` is the
*master* course numbering. When a runner's fork skips a master control, that
`cn` is **absent** from their controls (the sequence jumps, e.g. …7, 9, 10…),
and the split *into* the next control is blanked (`cd="-"`), because it spans
the skip and isn't comparable.

To compare fairly (this matches the official split view **exactly** — rank and
field size, validated 9/9 on a sample leg):

1. **Rank splits within `(legnro, cc_from, cc_to)`** — only runners who ran that
   exact physical segment on that leg. Keying on control *codes* (not `cn`)
   makes it fork-safe; restricting to one leg matches authority.
2. **Only legs with a valid `result` feed the comparison pool.** A mispunched
   leg's splits don't rank others (but that runner is still ranked *against* the
   pool on their own page).
3. **Don't fabricate a split across a fork boundary.** A split is only
   meaningful between consecutive master controls (`cn == prev_cn + 1`).
   Otherwise blank it (same as the source `cd="-"`).

## Computing common things correctly

- **Leg rank**: rank `tsecs` among all legs with the same `legnro` that have a
  result. Field ≈ 1579–1842 depending on leg.
- **Position at an exchange (after leg k)**: rank the cumulative sum of leg
  `tsecs` for legs 1..k, among teams whose chain 1..k is unbroken. A mispunch
  drops a team out of the running standings from that leg on. This is the
  *exchange order*, not the live mass-start clock.
- **Winner reference time**: use the official winning `result`/`tsecs`
  (min over ranked teams), NOT the sum of split-derived leg times — they drift a
  few seconds (mass start / rounding).
- **"Mistake" / time lost on a split**: gap to the segment's best time. Use a
  low-percentile "best" (~2nd pct) rather than the raw minimum to resist a
  single fluke-fast punch.

## How this repo consumes it

`jukola/parse.py` streams the file with `iterparse` (memory-bounded, ~1.6 s for
parse + aggregates). `jukola/analyze.py` builds the field aggregates and
per-team insights; `jukola/render.py` emits one static HTML page per team. See
`jukola/model.py` for the dataclasses and the same field notes.
