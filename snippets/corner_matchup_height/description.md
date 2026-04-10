# Corner Matchup Height — Far-Post Share vs Opponent Height

## What it does

Re-computes the far-post-share scatter embedded in the *Offense* section
of the [BAR-SP wiki page](): for every Barcelona match this snippet
measures how often Barcelona's corner deliveries landed at the far post
and plots that share against the raw top-6 outfield-player height gap
between the two sides.

The wiki argues that Barcelona's use of the far-post zone is selective
rather than systematic — essentially a counter-measure the side reaches
for either against a clear aerial mismatch (Newcastle, Slavia Praha) or
against an unusually short opponent (København). In every other league
phase match in the campaign Barcelona's corners avoided the far post
entirely. This script reproduces that finding from the raw event +
lineup JSONs.

## Inputs

- **Team name** (first positional CLI arg, default: `"Barcelona"`)
- **Output path** (second positional CLI arg, default:
  `./matchup_far_post_share.png`)
- **Data sources**: `data/matches.csv` plus StatsBomb event *and* lineup
  files streamed out of `data/statsbomb/league_phase.zip` and
  `data/statsbomb/playoffs.zip`. `data/statsbomb/last16.zip` ships
  without lineup files so the two Newcastle Round-of-16 fixtures are
  silently skipped — consistent with the wiki numbers.

## Output

One PNG scatter plot (`matchup_far_post_share.png` by default) plus a
stdout table listing every Barcelona match that made it through the
lineup filter, its corner count, far-post count, far-post share and
per-match top-6 height gap. The slope and intercept of the linear fit
line are also printed.

## Example outputs

### `matchup_far_post_share.py`

```
Barcelona matches with lineup + corner data: 7

  Opponent               n_corn far_post   share  focus_h   opp_h      Δh
  ----------------------------------------------------------------------
  Newcastle United            4        1   0.250    185.8   193.3    +7.5
  PSG                         4        0   0.000    186.3   186.7    +0.3
  Olympiacos Piraeus          7        0   0.000    185.2   185.5    +0.3
  Club Brugge                 3        0   0.000    184.8   187.2    +2.3
  Frankfurt                   5        0   0.000    184.8   186.7    +1.8
  Slavia Praha                4        0   0.000    185.3   190.2    +4.8
  København                  10        3   0.300    186.3   185.7    -0.7

Linear fit: far_post_share = +0.00754 * height_gap + +0.0608
Plot saved to matchup_far_post_share.png
```

## Definitions

- **Top-6 outfield height**: arithmetic mean of the 6 largest
  `player_height` values among outfield players (non-goalkeeper, with
  at least one position assignment in the lineup) for that match, read
  from the StatsBomb lineup JSON.
- **Height gap**: opponent top-6 height minus Barcelona top-6 height.
  Positive values mean the opponent is taller on average.
- **Far-post zone**: a meaningful-delivery endpoint with `x ≥ 114` and
  `y > 47` on the 120×80 StatsBomb pitch (mirrored around `y = 40`
  before classification so corners from both sides map to the same
  half of the 6-yard box).
- **Far-post share**: number of Barcelona corners in a match whose
  meaningful delivery landed in the Far-post zone divided by the total
  number of Barcelona corners in that match.
- **Meaningful delivery**: for direct corners the corner pass itself;
  for short corners (`pass.length ≤ 15 yd`) the first subsequent
  Barcelona pass or shot that actually delivers the ball into the box
  (pass end `x ≥ 96`, event start `x ≥ 105`, or pass length `≥ 12 yd`)
  — same rule as the source analysis in [`src/offense/barcelona_offensive_corners.py`]().
- **Matches skipped**: Round-of-16 fixtures (no lineup JSON in
  `last16.zip`) and any match in which the focus team took no corners
  at all (far-post share is 0/0 and therefore undefined).
- **Spelling drift**: team-name lookup is exact-match only. Teams whose
  `matches.csv` spelling differs from their StatsBomb-event spelling
  (PSG, Bayern, Monaco, Leverkusen, Dortmund) would be dropped here,
  but Barcelona is consistent across both sources so no Barcelona
  matches are lost to this filter.
