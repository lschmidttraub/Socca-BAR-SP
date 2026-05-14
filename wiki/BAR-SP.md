<details>
<summary>Project Group</summary>

| handle | name |
|--------|------|
| @leoschmidt     | Leo Schmidt-Traub |
| @kdanchishin     | Kirill Danchishin |
| @pvonder     | Philipp von der Thannen |
| @nwessbecher    | Niklas Weßbecher |
| @mwoeltje     | Merlin Wöltje |

- [x] check this if your final results may be shared with clubs, associations, or companies

</details>

<details>
<summary>TA Comments(Last edited: 21.04.2026)</summary>

Your teaching assistant is Luca Schnyder ( @schnyderl ) and can be reached at <schnyderl@student.ethz.ch>

- [ ] when saving, please indicate what you have changed in a meaningful commit message
- [x] first assignment due: **March 12**
- [x] second assignment due: **April 12**
- [ ] report and poster due: **May 24**

**(21.04.2026)**
Congratulations! You have reached the second milestone. For the final report, you should write a well-structured, coherent document. Ideally, this should include an introduction, various hypotheses, your analyses, and conclusions or recommendations regarding the team.
You are also welcome to design the team page together with the other three groups. For the final report, the hints should be removed, as well as any elements from the first two assignments in case they are no longer needed. Furthermore, there should be no code or documentation about the code in the report. Put it in a code snippet for example.
The analyses should not merely be a "tick-box" exercise of bullet points. Instead, identify any anomalies in the team's playing style and, if you find anything interesting, feel free to examine it in more detail with further analysis. Remember Ben Shneiderman's data visualization mantra: “Overview first, zoom and filter, then details-on-demand.”
All graphics should follow a consistent style so that readers can immediately identify the most important information. Ensure the report remains cohesive by using a unified background, consistent formatting, and appropriate colors for your team versus the opponent. Please also maintain a consistent pitch orientation (e.g., defense at the bottom/left and attack at the top/right).
Now, regarding your second assignment:
Very good approach. I really like that you looked at existing analysis and articles and create a story how the tactics has changed under Flick. Your analysis is very clean, you compared your values with other teams to get context to the numbers and the interpretation is also very good.  Keep up the good work! I don't have much to criticize here. Be consistent with your plots, for example: keep all pitches white. Also be careful when you make a final conclusion based on only few examples. I know that you don't have much data, but if you have time, definitely take the knockout games into account too, to increase the sample size and make your conclusion more robust.

**(16.03.2026)**

Congratulations, you have successfully completed your first assignment! It's great that you went beyond the minimum, keep it up!
The first assignment was designed to familiarize you with GitLab, encourage you to make use of the data and document the steps you took to reach your result, and perhaps visit other groups' pages. As this was a rather elementary analysis, note that the results of this first assignment can but do not have to stay on your page.
Looking forward to the second assignment: The core intention will be to practice the documentation and interpretation analysis. This serves as an opportunity to meet the requirements of documenting analyses for replication and interpreting your results meaningfully. Please approach this round of analysis with high quality, such that you may find it suitable to include directly in your final report later. Interpretation means providing contextualized meaning rather than simply pointing out which numbers are larger/smaller than others. It involves explaining results and translating those findings into meaningful conclusions. (That's also where GenAI often fails).
If you gather general informations or conduct analyses about the team that aren't directly related to your assignment, add them to the team page and collaborate with the other groups to create this page. This is highly encouraged and will also be considered.

Additionally, I'd also like to point out the following:

1) If you choose to create subpages, please make it easier for us to find them by always 1) link them in your group's main page and 2) ensuring that they appear as subpages of your main page in the wiki structure. This can be done by specifying the path of your subpage. Eg, if you are team AJX AD (with page path AJX-AD) and want to create a passing subpage, your subpage should have the path AJX-AD/passing.
2) All code snippets should be entered into the snippet repository [here](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/snippets). Please ensure you follow all the guidelines [here]( https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/snippet-overview) when detailing your code. Refer to the provided $2642 or $2643 snippets for examples of what is expected. If your snippet is something new and helpful for other teams, feel free to add it to the [snippet overview page](/snippet-overview) so that other teams can find it more easily.
3) When writing your analysis, always reference the code snippets you used by including $[snippet_id] in your text—this applies whether your team created the snippet or it came from another team. Additionally, when you create a new snippet, make sure to link back to your analysis page so that other teams can see the snippet in context and understand what it does.
4) Please enter meaningful commit messages instead of using the default “Update [page name]“. As your report will grow the lack of appropriate commit messages makes it very hard for your TA to keep track of what has changed on your page.

5) As a reminder, please be extremely careful when using AI tools with the dataset. The data has been shared with us under the strict condition that it must not be leaked or distributed outside the ETH Zurich environment. You may keep a local copy on your machine for analysis, but the dataset must not be uploaded to external platforms or third-party cloud services (e.g., Google Colab, Google Drive). If you would still like to use AI tools, ETH provides access to certain options within a protected environment. Please refer to: <https://ethz.ch/en/the-eth-zurich/education/ai-in-education/tools.html>. In particular, ETH offers Microsoft Copilot in this protected setup (note that this is not the same as GitHub Copilot).

If you have any more questions, don't hesitate to contact me or stop by at the open lab hours (Q&A session) on Wednesday from 12-14h at LEE D101.

</details>

**Disclaimer:** Generative AI was used to generate the plots in this report.

**Current status:** This report is not final, and will be updated as we progress. It does however outline the planned structure of the final report, and the example analyses included already reflect, to a large extent, the level of depth targeted in the final version. To keep a clean commit history, we do most of our work in a public repository, which can be found [here](https://github.com/lschmidttraub/Socca-BAR-SP).

## FC Barcelona's Set-Piece Identity in the UEFA Champions League 2025/26

### Introduction, Hypotheses and Approach

This introductory section motivates the analysis of FC Barcelona's set pieces by linking the club's traditional possession identity with the more direct and vertical style associated with Hansi Flick.
It reviews previous tactical analyses that describe Barcelona's set pieces as structured tools for defensive manipulation, while also identifying recurring defensive vulnerabilities around hybrid marking.
From these reports, we derive the main offensive and defensive expectations that guide the later data analysis and define the analytical scope.

| Section                                                                                                     | Description                                                                                                                                                                                                         |
|-------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [Motivation and Context](BAR-SP/introduction#introduction-review-of-existing-analyses-and-plan-of-analysis) | Introduces why Barcelona's set pieces are relevant under Hansi Flick and explains why corners and free kicks provide a useful entry point for analysing their current tactical development.                         |
| [Review Findings on Offensive Set-Pieces](BAR-SP/introduction#review-findings-on-offensive-set-pieces)      | Summarises previous analyses of Barcelona's attacking set pieces and derives the main hypotheses around short-corner manipulation, far-post access, coordinated runs, knockdowns, and second-ball structures.       |
| [Review Findings on Defensive Set-Pieces](BAR-SP/introduction#review-findings-on-defensive-set-pieces)      | Reviews reported weaknesses in Barcelona's defensive set-piece structure, especially hybrid marking, orientation loss, runner-marker separation, and vulnerability to far-post, near-post, and edge-of-box attacks. |
| [Plan of the Analysis](BAR-SP/introduction#plan-of-the-analysis)                                            | Defines the analytical scope, data basis, and methodological approach, combining statistical comparisons with qualitative sequence analysis while stressing the tournament-specific nature of the conclusions.      |

### Overview of Set-Piece Statistics

This examination of Barcelona's set-piece statistics reveal a clear contrast between above-average attacking free-kick production and more moderate attacking corner output.
Defensively, the numbers point to strong suppression of shots and xG from both free kicks and corners, challenging the expectation of an obvious set-piece vulnerability.
Match-level variation and physicality comparisons add context, indicating that Barcelona's set-piece performance depends strongly on opponent and game state rather than on aerial dominance alone.

| Section                                                                                                            | Description                                                                                                                                                                                                 |
|--------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [Offensive Set-Piece Statistics](BAR-SP/statistics#offensive-set-pieces)                                           | Summarises Barcelona's attacking set-piece baseline, showing a clear contrast between above-average free-kick production and more moderate corner output.                                                   |
| [Defensive Set-Piece Statistics](BAR-SP/statistics#defensive-set-pieces)                                           | Reviews Barcelona's defensive set-piece numbers, where low conceded goals, xG, and shot rates suggest strong suppression from both free kicks and corners.                                                  |
| [Set-Piece Performance over FC Barcelona Matches](BAR-SP/statistics#set-piece-performance-in-fc-barcelona-matches) | Examines match-level variation, showing that Barcelona's corner threat depends strongly on context, while free-kick sequences provide more consistent attacking value.                                      |
| [Player Physicality](BAR-SP/statistics#player-physicality)                                                         | Places the set-piece findings in physical context, showing that Barcelona are below average in height and therefore depend more on structure, organisation, and spatial manipulation than aerial dominance. |

### Analysis of Offensive Set-Pieces

This section analyses FC Barcelona's offensive set-piece behaviour across corners, free kicks, throw-ins and penalties.
The main focus lies on whether Barcelona use these situations as structured attacking tools, especially through short-corner manipulation, far-post access and positional improvement after restarts.
The findings suggest that Barcelona's offensive set-piece value often comes less from direct first-contact dominance and more from controlled continuation and role-specific execution.

| Section                                                                                                                         | Description                                                                                                                                                                                                                                      |
|---------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [Corner Routine Profile and Output](BAR-SP/offense#offensive-corners)                                                           | Analyses Barcelona's attacking corner profile, showing a structured but not elite-output approach based on direct inswingers, short-corner alternatives, compact occupation, and second-phase value.                                             |
| [Individual Players involved in Corner Action](BAR-SP/offense#individual-players-involved-in-corner-action)                     | Examines corner takers, receivers, and OBV profiles, highlighting Raphinha's delivery dominance, Yamal's continuation-oriented value, and the flexible distribution of first-contact targets.                                                    |
| [Spatial Profile of Corner Delivery](BAR-SP/offense#spatial-profile-of-corner-delivery)                                         | Studies delivery zones, first-touch locations, far-post usage, and matchup effects, showing how Barcelona combine central danger with selected far-post and recycle options.                                                                     |
| [Attacking Players Movements on Corners](BAR-SP/offense#attacking-players-movements)                                            | Uses selected movement maps to interpret Barcelona's corner routines as compact, controlled, and sequence-oriented rather than based on large-scale choreography or pure aerial superiority.                                                     |
| [Free-kick Routine Profile and Output](BAR-SP/offense#offensive-free-kicks)                                                     | Evaluates Barcelona's attacking free-kick profile, where above-average goals, shot rate, and xG suggest stronger production than from corners, supported by a mixed and zone-dependent routine selection.                                        |
| [Individual Players involved in Free-kick Action](BAR-SP/offense#individual-players-involved-in-free-kick-action)               | Compares free-kick takers, receivers, OBV distributions, and player-specific delivery maps, showing a more situational responsibility structure than for corners.                                                                                |
| [Spatial Profile of attempt-oriented Free-kick Delivery](BAR-SP/offense#spatial-profile-of-attempt-oriented-free-kick-delivery) | Separates crossed and direct free kicks, linking crossed deliveries to the corner hypotheses around second actions while treating direct shots as a more individual execution-based threat.                                                      |
| [Free-kicks From the "Dead Zone"](BAR-SP/offense#free-kicks-from-the-dead-zone)                                                 | Analyses OBV changes after deeper free-kick restarts, showing how Barcelona use these situations to reset structure, switch play, and improve possession rather than attack goal directly.                                                       |
| [Throw-ins](BAR-SP/offense#throw-ins)                                                                                           | Interprets Barcelona's throw-ins as positional tools, with strong possession retention and side-changing behaviour but limited direct xG creation from advanced throw-ins.                                                                       |
| [Penalties](BAR-SP/offense#penalties)                                                                                           | Reviews Barcelona's four penalties through taker routines, shot placement, keeper behaviour, and rebound positioning, while stressing that the sample is too small for general performance claims.                                               |
| [Conclusion and Recommendations](BAR-SP/offense#conclusion-and-recommendations)                                                 | Connects the offensive findings back to the hypotheses from previous analyses and derives recommendations around short corners, second-phase routines, far-post usage, crossed free kicks, dead-zone progression, and penalty rebound structure. |

### Analysis of Defensive Set-Pieces
