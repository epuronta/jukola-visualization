# Jukola insights generator

PY     ?= python3
XML    ?= results_j2026_ju.xml
OUT    ?= out
# TEAM has no default on purpose: never bake a specific team id into the repo.
# Pass it on the command line, e.g. `make team TEAM=123`.
TEAM   ?=
CHROME ?= /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
WIN    ?= 960,2600

.PHONY: team all preview shot open clean require-team

require-team:
	@test -n "$(TEAM)" || { echo "set TEAM=<teamid>, e.g. make $(MAKECMDGOALS) TEAM=123"; exit 1; }

# Render one team page (make team TEAM=123)
team: require-team
	$(PY) -m jukola.generate --xml $(XML) --out $(OUT) --team $(TEAM)

# Render every team page
all:
	$(PY) -m jukola.generate --xml $(XML) --out $(OUT) --all

# Render a team and grab a screenshot (make preview TEAM=123)
preview: team shot

# Screenshot the current team page into out/preview.png
shot: require-team
	"$(CHROME)" --headless --disable-gpu --hide-scrollbars \
		--window-size=$(WIN) \
		--screenshot=$(OUT)/preview.png \
		"file://$(CURDIR)/$(OUT)/$(TEAM:%=team_%.html)" 2>/dev/null
	@echo "wrote $(OUT)/preview.png"

# Open the current team page in the default browser
open: require-team
	open "$(OUT)/team_$(TEAM).html"

clean:
	rm -rf $(OUT)
