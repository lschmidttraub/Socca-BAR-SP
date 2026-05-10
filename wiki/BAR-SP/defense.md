# Defensive Analysis

## Defensive Corners


## Defensive Free-kicks
As already mentioned in the [statistics section](BAR-SP/statistics#defensive-free-kick-sequences), Barcelona conceded 1 goal from free-kicks, which is less than the competition average of 1.94.
This finding is also reflected in their average xG conceded from free-kick sequences per game which is only 0.091, far below the mean of 0.183 [(stat-df2)](BAR-SP/statistics_plot#average-conceded-xg-from-free-kicks-per-game---barcelona-below-average).

In light of this information, defensive free-kicks are one of Barcelona’s clearest strengths.

### Added Value of Defensive Free-kicks
So the overview seems positive, but let us take a more granular look at the added value of defensive free-kicks.
In the plot below, we show, from left to right, heatmaps of xG, fouls, and opponent obv for all free-kicks in Barcelona’s defensive half.
<img src="assets/upload/defensive/free-kicks/foul_freekick_xg_heatmap.png" width="100%" />

TO BE IMPROVED/MADE INTO A CONTINUOUS TEXT 
These pictures paint an interesting picture:
1. The xG/OBV doesn't tell the whole story: if the opponent was previously in a more dangerous position, a free-kick can represent a net gain for the defending team. A better way of analyzing this is to look at the change in opponent's OBV from the play leading up to the free-kick to the moment following the free-kick. 
2. This perspective helps us see how free-kicks are used in Barcelona's defensive strategy: they allow the team to mitigate dangerous situations.
3. The new picture flips the left-right asymmetry: though free-kicks on the left side of the field are more dangerous, their net effect on the OBV is more positive than right-side free-kicks.
4. This tradeoff is further emphasized by the foul heatmap: more fouls are committed on the right side, and are committed further away from the goal. Thus, a more aggressive defensive strategy leads to more premature fouls, which decreases the absolute danger, but represents a more worse OBV trade.  
5. TODO: attach this to the players + Flick's overarching strategy
The code for this plot can be found in snippet UNKNOWN. The first plot was inspired by the RMA-SP group's snippet $3111.



