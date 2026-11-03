# Award Odds Tracker

[![Tests](https://github.com/rykaracebo/data-tracker-project/actions/workflows/tests.yml/badge.svg)](https://github.com/rykaracebo/data-tracker-project/actions/workflows/tests.yml)

Every day, on its own, this tool downloads sportsbook odds for **NBA, NFL and college football
awards and title favorites**, together with the stats behind each race. It keeps a history with one
row per item per day, reports what moved, opens a GitHub Issue about it, and publishes the result
as an installable website.

- **Live site:** `https://rykaracebo.github.io/data-tracker-project/`
- **Data:** [`data/history.csv`](data/history.csv) and [`data/status.json`](data/status.json)

Built for the Financial Data Analytics data tracker project, with Claude Code.

## What is tracked

13 markets, and in each the **ten shortest prices** (the ten likeliest winners), so up to 130 items a day. The long tail of longshots (a market can have 90 candidates) is not tracked. Prices are DraftKings' American odds as published by ESPN.

| League | Market | Who wins it | Stats kept with each item |
|---|---|---|---|
| NBA | MVP, Rookie of the Year, Defensive Player of the Year | a player | MVP, ROY: points, rebounds, assists per game. DPOY: blocks, steals per game |
| NBA | Coach of the Year | a coach | the coach's team win % |
| NBA | Finals winner | a team | win %, points for, points against |
| NFL | MVP, Offensive Player of the Year, Offensive Rookie of the Year | a player | passing, rushing, receiving yards, touchdowns |
| NFL | Defensive Player of the Year, Defensive Rookie of the Year | a player | tackles, sacks, interceptions |
| NFL | Super Bowl winner | a team | win %, points for, points against |
| College football | Heisman Trophy | a player | passing, rushing, receiving yards, touchdowns |
| College football | College Football Playoff champion | a team | win %, points for, points against |

The **key** that lines an item up from one day to the next is `item_id`:
`<league>-<award>-<ESPN id>`, for example `nba-mvp-3945274` or `nfl-sbwin-2`. The same
person can be in several markets (an NBA player in both MVP and DPOY), so the award is part of the key.

## Sources

All sources are public ESPN JSON endpoints that need no login and no API key, so nothing secret is stored.
Raw files are saved gzipped, in the format they came in, at `data/raw/<date>/<source>.json.gz`.

| Source (file name) | Format | What it is | What is kept |
|---|---|---|---|
| `nba_futures`, `nfl_futures`, `ncaaf_futures` | JSON | The DraftKings futures board for the league. One call returns every market | **Only the tracked markets, and in each only the ten shortest prices.** The saved file keeps the board's JSON shape, cut down |
| `nba_athletes`, `nfl_athletes`, `ncaaf_athletes` | JSON | One player or coach record per tracked candidate (name, team), found through the links on the futures board | Every tracked candidate's full record. Written as one file: `{"athletes": {id: record}}` |
| `nba_stats` | JSON | NBA per-game season stats. One call lists every NBA player (about 300) | **Only the tracked candidates** (about 77 players) are kept, and the explanatory glossary is dropped |
| `nfl_stats`, `ncaaf_stats` | JSON | Season stats, one call per candidate (the league-wide list is thousands of players) | Only the stat categories used (general, passing, rushing, receiving, defensive, interceptions), and each stat's name and value only. One file: `{"athletes": {id: record}}` |
| `nba_standings`, `nfl_standings` | JSON | Standings: team names, win %, points for and against | All of it, as received |
| `ncaaf_teams` | JSON | Team records for the teams of the tracked players and of the playoff market, for names and codes | One file: `{"teams": {id: record}}` |
| `ncaaf_records` | JSON | Each playoff-market team's overall record and points (the college standings feed only has conference stats, so it is not used) | Only the "overall" record's stat names and values. One file: `{"teams": {id: record}}` |
| `nba_coaches` | JSON | Which team each NBA coach belongs to (one call for each of the 30 teams) | One file: `{"teams": {team_id: response}}` |

If a source stops working it will be replaced by another. Where a source returns far more than is tracked
(NBA players, football players), only the tracked part is kept, as listed above.

## The daily run

[`.github/workflows/daily.yml`](.github/workflows/daily.yml) runs `python -m tracker.run` once a day (09:23 UTC) and then:

1. **Calls every source** and saves what it returned. One source failing does not stop the run: it writes no
   raw file that day, and its result (`ok`, `count`) is recorded in `data/status.json`. Details of every
   failure, with the error text, are appended to `data/run_log.jsonl`.
2. **Builds the history** from the raw files (below).
3. **Writes `data/status.json`.**
4. **Opens a GitHub Issue** titled `<date> award odds moves` that lists the biggest moves with old and new
   values, and any item that appeared or disappeared, and closes the previous day's Issue. It is opened
   every day, even when nothing changed.
5. **Commits** the raw files, the history and the status file.

A run counts as successful when it finishes and commits, even if some sources failed. A second run on the
same UTC date replaces that date's raw files, rebuilds the history and updates that day's Issue, so each day
counts once. The workflow can also be started by hand from the Actions tab.

## Build the history from the raw files

```
python -m tracker.build
```

This reads only `data/raw/` and rewrites `data/history.csv`. Running it again gives the same bytes, and if a
rule in `tracker/convert.py` or `tracker/build.py` changes, the change applies to every day. The top-ten rule is
applied again here, so a raw file holding a longer board gives the same history. A source with
no raw file on a day gives no rows from that league that day. A value a source does not report for an item
is left empty. Rows are sorted by date, then `item_id`. If a day's athlete file is missing, names come from
the earlier days; if there never was one, the name is the ESPN id.

## The history file: `data/history.csv`

One row per item per day. Dates are UTC (`YYYY-MM-DD`).

| Column | Meaning | Unit |
|---|---|---|
| `date` | The UTC date of the run | `YYYY-MM-DD` |
| `item_id` | Key of the item: `<league>-<award>-<ESPN id>` | text |
| `item` | The item's name (player, coach or team) | text |
| `source` | The raw source the row comes from: `nba_futures`, `nfl_futures` or `ncaaf_futures` | text |
| `league` | `nba`, `nfl` or `ncaaf` (college football) | code |
| `award` | NBA: `mvp`, `roy`, `dpoy`, `coy`, `finals`. NFL: `mvp`, `opoy`, `dpoy`, `oroy`, `droy`, `sbwin`. College: `heisman`, `cfp` | code |
| `team` | The item's team code (for a team market, the team itself) | code, e.g. `BUF` |
| `odds` | DraftKings' price, American odds. `+200` wins 200 on a 100 stake, `-150` needs 150 to win 100 | American odds |
| `implied_prob` | The probability the odds imply: `100 / (odds + 100)` for plus odds, `-odds / (-odds + 100)` for minus odds. Not adjusted for the sportsbook's margin | fraction, 0 to 1 |
| `gp` | Games played so far this season | games |
| `ppg`, `rpg`, `apg` | NBA points, rebounds, assists per game (MVP, ROY) | per game |
| `bpg`, `spg` | NBA blocks, steals per game (DPOY) | per game |
| `win_pct` | The team's win percentage, from standings or the overall record. For a coach, the coach's team | fraction, 0 to 1 |
| `pass_yds`, `rush_yds`, `rec_yds` | Season passing, rushing, receiving yards (football players) | yards, season total |
| `td` | Touchdowns passed, rushed or caught (return touchdowns are not counted) | count, season total |
| `tackles` | Total tackles (solo plus assisted) | count, season total |
| `sacks` | Sacks | count, season total (halves allowed) |
| `ints` | Interceptions caught by a defender | count, season total |
| `pts_for`, `pts_against` | Points a team has scored and allowed (team markets) | points, season total |

A cell is empty when the source does not report that value for the item that day (a player who has not
played yet has no stats) or when the column does not apply to that market.

## The status file: `data/status.json`

| Key | Meaning |
|---|---|
| `run_time` | When the latest run happened (UTC) |
| `first_run_date` | The date of the earliest raw file |
| `days_with_success` | The number of different dates with a raw file |
| `items` | The number of items in the latest run (rows for that date) |
| `new_today` | `item_id`s that appeared: on today's board but not the previous day's |
| `gone_today` | `item_id`s that disappeared: on the previous day's board but not today's |
| `sources` | One entry per source: `name`, `ok` (true or false), `count` (items the source gave) |

`new_today` and `gone_today` are empty on the first day, and on a day with no rows (so a failed source cannot
make every item look gone).

## The move rule

**Move = today's implied probability minus the previous day's, in percentage points.**

- An item is compared only if it has a price on both days.
- The **10 items with the biggest absolute move** are listed in the Issue and on the Today page, largest
  first (ties are broken by `item_id`). Items whose probability did not change are not listed.
- An item on today's board that was not on the previous day's **appeared**; one on the previous day's board
  that is not on today's **disappeared**. Both are listed in the Issue. Because only the ten shortest prices in
  each market are tracked, an item **appears** when its price moves into the top ten and **disappears** when it
  drops out.

The same rule is written in Python (`tracker/moves.py`) and in JavaScript (`computeMoves` in
`assets/common.js`), so the Issue and the site agree.

## The site

Served by GitHub Pages from the repository root. All three pages load `data/history.csv` and
`data/status.json` in the browser and do their calculations there.

- **Today** (`index.html`): time of the last run, status of every source, the counts, the latest values of every
  item with their change since the previous run, and the biggest moves.
- **Browse** (`browse.html`): filters (league, market, team), name search, sort on every numeric column up and down,
  and a star on every item that saves it to a shortlist kept in the browser (it survives a reload).
- **Trends** (`trends.html`): a chart of each numeric value over the days with a control for picking items, and
  eight sections whose headings state a finding computed from the history (who rose most, the busiest day, how
  one-sided each race is, whether stats line up with prices, ...). Each says how its numbers are computed.

The site is installable (web app manifest and a service worker). Online, the pages fetch the data files from
the network; offline, the service worker answers from its cache, so the site still opens with the last data it loaded.

## Files

| Path | What it does |
|---|---|
| `README.md` | This file |
| `requirements.txt` | Python packages for the tests (`pytest`). The pipeline itself uses only the standard library |
| `.gitignore` | Files git ignores (virtual environment, caches) |
| `.nojekyll` | Tells GitHub Pages to serve the files as they are |
| `index.html`, `browse.html`, `trends.html` | The three site pages |
| `manifest.webmanifest` | Web app manifest that makes the site installable |
| `sw.js` | Service worker: network first, saved copy when offline |
| `assets/style.css` | The one set of fonts and colors (light and dark) used by all pages |
| `assets/common.js` | Shared code: loading the data, number formatting, the move rule, the shortlist, the navigation bar |
| `assets/charts.js` | Small SVG chart library (line, bar and scatter charts with tooltips) |
| `assets/index.js`, `assets/browse.js`, `assets/trends.js` | The code of each page |
| `assets/icon-192.png`, `assets/icon-512.png`, `assets/icon-maskable-512.png` | App icons |
| `tracker/config.py` | Leagues, markets, columns and which stats each market carries |
| `tracker/fetch.py` | Downloads the sources; never raises, so one failure cannot stop a run |
| `tracker/convert.py` | Turns each source's raw JSON into the common values (odds math, stats, standings, ...) |
| `tracker/build.py` | Builds `data/history.csv` from the raw files (`python -m tracker.build`) |
| `tracker/moves.py` | The move rule |
| `tracker/status.py` | Builds and writes `data/status.json` |
| `tracker/issues.py` | Creates or updates the daily Issue and closes the previous one |
| `tracker/run.py` | One daily run: fetch, save raw files, build history, write status (`python -m tracker.run`) |
| `tests/` | The pytest suite: conversion of each source, the move rule, the history logic including a second run on the same day, the fetchers and the Issue |
| `tools/make_icons.py` | Draws the app icons |
| `.github/workflows/daily.yml` | The daily run (schedule, plus a button to run it by hand) |
| `.github/workflows/tests.yml` | Runs the tests on every push |
| `data/history.csv` | The history, one row per item per day |
| `data/status.json` | Describes the latest run |
| `data/run_log.jsonl` | One line per run with every source's result and any error text |
| `data/raw/<date>/<source>.json.gz` | What every source returned that day |

## Run it yourself

```
python -m tracker.run        # fetch everything, rebuild the history, write the status file
python -m tracker.build      # rebuild only the history from data/raw
pip install -r requirements.txt && python -m pytest
python -m http.server        # then open http://localhost:8000
```

## Tests

`python -m pytest` runs the suite, and the **Tests** workflow runs it on every push. It covers the conversion
of each source to the common columns, the move rule, and the history logic: sorting, empty values, names from
earlier days, a rebuild reproducing the same file, and a second run on the same day replacing that day.
