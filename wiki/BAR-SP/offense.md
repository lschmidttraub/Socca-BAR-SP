<!--
**TODO:**

 - Adapt the content to the final numbers, when all data is available
 - Conduct analyses as described below
 -->

## Offensive Analysis
### Offensive Corners

The first key finding is that Barcelona’s corner strategy appears structurally distinctive, even if the overall output is not elite. 
Earlier overview results showed that Barcelona were below the competition average in attacking-corner xG, attempts, and goals.
However, the present visuals suggest that this does not reflect a random or underdeveloped corner approach. 
Instead, Barcelona seem to rely on a designed attacking model built around direct inswing deliveries, and a meaningful but secondary use of short corners and first-contact manipulation rather than through clear aerial dominance. 

This is already visible in the routine distribution. Of Barcelona’s offensive corners, 31 were direct inswingers, 11 were short corners, 4 were other direct deliveries, and only 1 was a direct outswinger. 
This suggests that inswing corners form the default structure, while short corners serve as an important alternative. 
Barcelona therefore combine traditional delivery with selective short-corner routines to disrupt defensive organisation.

The efficiency metrics refine this picture. 
Barcelona generate more attempts per corner from short corners than the average team, whereas crossed corners produce fewer shots than average. 
A similar pattern appears in xG per corner: both routine types are slightly below average, but the gap is smaller for short corners.
This suggests that short corners are a relatively effective shot-creation mechanism for Barcelona, even if they do not fully compensate for the team’s lower overall corner output. 
In this sense, short-corner routines may act as tactical approach to help offset Barcelona’s weaker physical profile.

|                             Attempt Rate                             |                          xG per Corner                          |
|:--------------------------------------------------------------------:|:---------------------------------------------------------------:|
| ![](assets/upload/offensive/corners/attempts_per_corner_bars.png) | ![](assets/upload/offensive/corners/xg_per_corner_bars.png) |

Raphinha clearly dominates as the corner taker, indicating a high level of delivery execution consistency.
By contrast, receivers and first shooters are more widely distributed across several players, mainly Center Backs and Strikers.
This points to a strategy based on coordinated movement and role allocation rather than on one fixed aerial target. 
Delivery is standardised, but reception and finishing remain flexible.

|            Top Takers of Barcelona's Corners             |                  Top Receivers of Barcelona's Corners                  |
|:--------------------------------------------------------:|:----------------------------------------------------------------------:|
| ![](assets/upload/offensive/corners/corner_takers_single.png) | ![](assets/upload/offensive/corners/delivery_receivers_single.png) |

The spatial maps deepen this reading, illustrating clear but not exclusive tendencies for areas of delivery. 
Many deliveries are directed into the central six-yard area and near-post corridor, with a smaller overall share toward the far post, the edge of the box, and wider recycle zones. 
Barcelona therefore do not attack only one target area.
Interestingly, the far-post option seems to be a real option for right-side corners.
Instead, they appear to combine dangerous first-contact zones close to goal with the possibility of recycled possession or a second delivery.

![](assets/upload/offensive/corners/spatial_profile.png)
<figcaption  style="margin: 0 0 20px 5px">Spatial Profile (normalized to left-side) - Two main target zones visible</figcaption>

![](assets/upload/offensive/corners/delivery_endpoints_by_side.png)
<figcaption  style="margin: 0 0 20px 5px">Delivery endpoints by side - Long corners predominantly used from the right</figcaption>

This is also reinforced by the map of first touches after offensive corners. 
After the initial contact, Barcelona usually (especially from the left side) continue the sequence with a pass-on or carry, especially from wider or more advanced positions.
Direct attempts (mostly headers) are rather common when right-side corners are executed.
This suggests that their corners should not be evaluated only through the first header or shot, as an important part of the attacking value emerges in the second phase, which even might be decoupled from the initial corners xG etc. values.
The goal-sequence maps illustrate this clearly. 
The presented goal result from multi-action sequences rather than direct finishes from the original delivery. 
This supports the broader interpretation that Barcelona’s corner strategy is based less on raw aerial superiority and more on controlled second-phase construction.

![](assets/upload/offensive/corners/corner_first_touch_map.png)
<figcaption  style="margin: 0 0 20px 5px">First Touch Map - Sequences often continue with pass-on or carry</figcaption>

The far-post-share plot adds a potentially interesting contextual detail regarding physicality and corner strategy. 
Barcelona’s use of the far-post zone appears to increase particularly against the most extreme opponents in terms of height, namely Newcastle, by far the tallest team in the competition, and Copenhagen, the only shorter team with a height disadvantage in their match against Barcelona.
Although the sample is limited, this supports the idea that Barça may use the far post to avoid central aerial duels when in clear height disadvantage combined with a path strategy and to exploit their advantage against shorter teams.
This observation is particularly significant, as in all other games, corner were never delivered to the far-post.

![](assets/upload/offensive/corners/matchup_far_post_share_single.png)
<figcaption  style="margin: 0 0 20px 5px">Share of far-post Corners - Selected strategy against Copenhagen (Kobe) and Newcastle (NU)</figcaption>

#### Movement of Attacking Players

Four particularly informative visualisations were selected for closer offesive corner movement analysis: two corner situations against Copenhagen and Praga that led to attempts, one corner against Newcastle that did not result in an attempt, and the goal sequence against Frankfurt.
The major part of all corner visualisations made suggests that Barcelona’s offensive corners are generally built on compact occupation and small coordinated adjustments, rather than on large, highly dynamic pre-delivery movement.

The visualised corner against Sparta Praha can be seen as one typical example:

![](assets/upload/offensive/corners/corner_2050711_01_right_2848_shot.png)
<figcaption  style="margin: 0 0 20px 5px">Corner Routes vs. Sparta Praha - Minimalistic Movements; created second-row attempt</figcaption>

Compared with the more patterned three examples against, the attackers show only limited displacement from their starting positions, and the routine appears to depend more on maintaining box occupation than on actively reshaping it. 
This supports the idea that Barcelona often prefer positional control over exaggerated choreography. 
Their corners are therefore not always built around dramatic decoy runs or sweeping movements across the box, but often around a more stable arrangement from which several players can attack the delivery or react to a second ball.

In the Copenhagen and the Newcastle examples below, the clearest pattern is a dense initial occupation of the six-yard box and near-post corridor, followed by short, curved, mainly vertical or diagonal runs into the goal area. 
The movement is compact rather than expansive and is designed to create separation in a very limited space, but definitely a distinct strategy to free a player at the far-post and put the defense into movement towards the goal.

![](assets/upload/offensive/corners/corner_2051683_04_right_1452_shot.png)
<figcaption  style="margin: 0 0 20px 5px">Corner Routes vs. Copenhagen - Movement to the near post; no attempt</figcaption>

![](assets/upload/offensive/corners/corner_2059201_05_right_3957_no_shot.png)
<figcaption  style="margin: 0 0 20px 5px">Corner Routes vs. Newcastle - Movement towards the goal; near-post header</figcaption>

The goal against Frankfurt provides the clearest example of how Barcelona can add a stronger manipulation layer to this compact structure using their short-played alternative. 
Here, the initial box occupation is again dense, but the subsequent movements show a more purposeful attempt to crowd the first zone, occupy defenders, and open a finishing space for the second action. 
Rather than aiming for a clean direct finish from the initial delivery, the routine creates a favourable central situation through congestion, redirection, and continuation of the sequence. 
This is consistent with the earlier goal-sequence maps, which already indicated that Barcelona’s goals from corners often emerge through more than one action rather than from a straightforward first-contact header.

![](assets/upload/offensive/corners/corner_2047362_03_left_5217_goal.png)
<figcaption  style="margin: 0 0 20px 5px">Corner Routes vs. Frankfurt - Short corner and spreading routed; goal</figcaption>

Taken together, these movement maps suggest that Barcelona’s offensive corner strategy is best described as compact, controlled, and sequence-oriented. 
Most routines rely on short, well-timed adjustments from a dense starting structure, while only some sequences show more clearly choreographed movement patterns. 
This interpretation fits the broader findings of the report. Barcelona’s corners are not especially strong because of high volume, exceptional corner xG, or superior physicality. 
Instead, their attacking value appears to come from the way they use local overloads, selective movement, and continuation after the first contact to create opportunities.

### Offensive Free-kicks

Planned Analysis:
  - Mirror the delivery and route analysis of corners (trajectory, target zones)
  - Also interpretation in the context of the defined hypothesis from the online review (comparison with corners)
  - Effectivness of direct free kicks (goal vs. FC Copenhagen)
  - OBV value analysis for free-kick in "dead zone"

### Penalties (to discuss)

Planned Analysis:
  - Penalty takers 
  - Game-changing potential

### Throw-ins

Planned Analysis:
  - throw-ins as offensive (delivery) instrument (heat map, OBV improvement analysis)
  - throw-ins as position instrument (turnover rate; improvement potential)