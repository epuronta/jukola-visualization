# jukola-visualization

Visualization of [Jukola](https://www.jukola.com/) orienteering relay results.

## Data

Results come as a single XML export (e.g. `results_j2026_ju.xml`), one event with
classes → teams → legs → controls. These files are large (~28MB) and are **not**
committed — they're gitignored (`results_*.xml`). Drop the export in the repo root
before running anything.

## Status

Early WIP. Logic is under active development.
