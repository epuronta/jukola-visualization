# jukola-visualization

Visualization of [Jukola](https://www.jukola.com/) orienteering relay results.

## Data

Results come as a single XML export per event (classes → teams → legs → controls).
They live under `data/<year>/<relay>.xml` (e.g. `data/2026/jukola.xml`), mirroring
the generated output tree, and are committed so the site can be built in CI.

The generated HTML under `docs/` is **not** committed — it is built from the XML by
the GitHub Actions workflow (`.github/workflows/deploy.yml`) and deployed to Pages.
Run `make all RELAY=jukola YEAR=2026` locally to build a single event.

## Status

Early WIP. Logic is under active development.
