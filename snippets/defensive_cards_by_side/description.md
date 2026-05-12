# Defensive Cards by Side — Left vs Right

## What it does

Tallies the yellow and red cards picked up by every defensive player of the focus team across the UCL 2025-26 campaign, and groups them by the side of the pitch they primarily play on (left vs right). Supports the discipline discussion on the [BAR-SP wiki page](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP) and highlights asymmetries between left- and right-side defenders — e.g. for FC Barcelona, the right-side back-line group (Cubarsí, Araújo, Eric García) absorbs every red card while the left-side group (Cancelo, Balde, Martín) accumulates the bulk of the yellows.

A player's side is determined from their most-frequent StatsBomb `position.name` across all events they featured in. Pure central defenders (`Center Back`) are kept off the left-vs-right comparison; left/right backs, wing-backs and center-back specialisations are split by side.

## Inputs

- **Team name** (first positional CLI arg, default: `"Barcelona"`)
- **Output path** (second positional CLI arg, default: `./defensive_cards_by_side.png`)
- **Data sources**: StatsBomb event data (`data/statsbomb/league_phase.zip`, `last16.zip`, `playoffs.zip`, `quarterfinals.zip`) and `data/matches.csv` as the match lookup.

## Output

1. **Stdout** — a table of every defensive player on the focus team with their primary position, side, yellow-card count and red-card count, plus per-side totals.
2. **PNG plot** — a two-panel stacked-bar chart (left side | right side); each player has one stacked bar (yellow + red). Card counts are written inside the segments and the per-player total above each bar.

![](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP/assets/upload/cards/defensive_cards_by_side.png)

## Example outputs

### `defensive_cards_by_side.py`

```
Defensive players' cards — Barcelona
  Matches counted: 12
------------------------------------------------------------------------
Side    Primary position     Player                         Y   R
------------------------------------------------------------------------
left    Left Center Back     Gerard Martín Langreo          2   0
left    Left Back            João Pedro Cavaco Cancelo      2   0
left    Left Back            Alejandro Balde Martínez       1   0
left    Left Center Back     Andreas Christensen            0   0
                             TOTAL left                     5   0
------------------------------------------------------------------------
right   Right Center Back    Pau Cubarsí Paredes            1   1
right   Right Center Back    Ronald Federico Araújo da Silva   1   1
right   Right Center Back    Eric García Martret            0   1
right   Right Back           Jules Koundé                   1   0
right   Right Back           Xavi Espart Font               0   0
                             TOTAL right                    3   3
------------------------------------------------------------------------

Saving plot to defensive_cards_by_side.png ...
  saved defensive_cards_by_side.png
```

## Definitions

- **Defensive player**: a player whose most-frequent `position.name` (computed across every event they appear in) is one of `Left Back`, `Left Wing Back`, `Left Center Back`, `Right Back`, `Right Wing Back`, `Right Center Back`, or `Center Back`. Defensive midfielders are excluded — the focus is on the back line.
- **Side classification**: `left` for `Left Back` / `Left Wing Back` / `Left Center Back`; `right` for the mirrored set. `Center Back` (pure, non-lateralised) is reported but kept out of the left-vs-right plot.
- **Yellow card**: each StatsBomb event with `bad_behaviour.card.name == "Yellow Card"` or `foul_committed.card.name == "Yellow Card"` charged to that player.
- **Red card**: any dismissal event for that player — i.e. a `"Red Card"` *or* a `"Second Yellow"` event (a second yellow always results in a sending-off, so it counts as a red on this scale).
- **Primary position**: the position name with the highest event count for that player across the campaign. Players who slide between sides match-to-match end up on whichever side dominates their event share.

## Disclaimer

Generative AI was used in the creation of both the code and documentation for this snippet.
