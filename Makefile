# Jukola/Venla insights generator

PY     ?= python3
XML    ?= results_j2026_ju.xml
DOCS   ?= docs
YEAR   ?= 2026
RELAY  ?= jukola
# TEAM has no default on purpose: never bake a specific team id into the repo.
# Pass it on the command line, e.g. `make team TEAM=123`.
TEAM   ?=
CHROME ?= /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
WIN    ?= 960,2600

# generated page path for the selected event/team
PAGE   = $(DOCS)/$(YEAR)/$(RELAY)/$(TEAM).html

.PHONY: team all index preview shot open clean require-team

require-team:
	@test -n "$(TEAM)" || { echo "set TEAM=<teamid>, e.g. make $(MAKECMDGOALS) TEAM=123"; exit 1; }

# Render one team page (make team TEAM=123 [YEAR=2026 RELAY=jukola])
team: require-team
	$(PY) -m jukola.generate --xml $(XML) --docs $(DOCS) --year $(YEAR) --relay $(RELAY) --team $(TEAM)

# Render every team page for the event, then rebuild the indexes
all:
	$(PY) -m jukola.generate --xml $(XML) --docs $(DOCS) --year $(YEAR) --relay $(RELAY) --all
	$(MAKE) index

# (Re)build the docs index pages from whatever has been generated
index:
	$(PY) -m jukola.index --docs $(DOCS)

# Render a team and grab a screenshot (make preview TEAM=123)
preview: team shot

# Screenshot the current team page into out/preview.png
shot: require-team
	@mkdir -p out
	"$(CHROME)" --headless --disable-gpu --hide-scrollbars \
		--window-size=$(WIN) \
		--screenshot=out/preview.png \
		"file://$(CURDIR)/$(PAGE)" 2>/dev/null
	@echo "wrote out/preview.png"

# Open the current team page in the default browser
open: require-team
	open "$(PAGE)"

# Remove generated pages for the selected event (keeps committed docs assets)
clean:
	rm -rf $(DOCS)/$(YEAR)/$(RELAY) out
