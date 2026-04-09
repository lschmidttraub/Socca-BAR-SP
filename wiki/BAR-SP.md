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
<summary>TA Comments(Last edited: 16.03.2026)</summary>

Your teaching assistant is Luca Schnyder ( @schnyderl ) and can be reached at <schnyderl@student.ethz.ch>

- [ ] when saving, please indicate what you have changed in a meaningful commit message
- [x] first assignment due: **March 12**
- [ ] second assignment due: **April 12**
- [ ] report and poster due: **May 24**

**(16.03.2026)**

Congratulations, you have successfully completed your first assignment! It's great that you went beyond the minimum, keep it up!
The first assignment was designed to familiarize you with GitLab, encourage you to make use of the data and document the steps you took to reach your result, and perhaps visit other groups’ pages. As this was a rather elementary analysis, note that the results of this first assignment can but do not have to stay on your page.
Looking forward to the second assignment: The core intention will be to practice the documentation and interpretation analysis. This serves as an opportunity to meet the requirements of documenting analyses for replication and interpreting your results meaningfully. Please approach this round of analysis with high quality, such that you may find it suitable to include directly in your final report later. Interpretation means providing contextualized meaning rather than simply pointing out which numbers are larger/smaller than others. It involves explaining results and translating those findings into meaningful conclusions. (That's also where GenAI often fails).
If you gather general informations or conduct analyses about the team that aren't directly related to your assignment, add them to the team page and collaborate with the other groups to create this page. This is highly encouraged and will also be considered.

Additionally, I’d also like to point out the following:

1) If you choose to create subpages, please make it easier for us to find them by always 1) link them in your group's main page and 2) ensuring that they appear as subpages of your main page in the wiki structure. This can be done by specifying the path of your subpage. Eg, if you are team AJX AD (with page path AJX-AD) and want to create a passing subpage, your subpage should have the path AJX-AD/passing.
2) All code snippets should be entered into the snippet repository [here](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/snippets). Please ensure you follow all the guidelines [here]( https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/snippet-overview) when detailing your code. Refer to the provided $2642 or $2643 snippets for examples of what is expected. If your snippet is something new and helpful for other teams, feel free to add it to the [snippet overview page](/snippet-overview) so that other teams can find it more easily.
3) When writing your analysis, always reference the code snippets you used by including $[snippet_id] in your text—this applies whether your team created the snippet or it came from another team. Additionally, when you create a new snippet, make sure to link back to your analysis page so that other teams can see the snippet in context and understand what it does.
4) Please enter meaningful commit messages instead of using the default “Update [page name]“. As your report will grow the lack of appropriate commit messages makes it very hard for your TA to keep track of what has changed on your page.

5) As a reminder, please be extremely careful when using AI tools with the dataset. The data has been shared with us under the strict condition that it must not be leaked or distributed outside the ETH Zurich environment. You may keep a local copy on your machine for analysis, but the dataset must not be uploaded to external platforms or third-party cloud services (e.g., Google Colab, Google Drive). If you would still like to use AI tools, ETH provides access to certain options within a protected environment. Please refer to: <https://ethz.ch/en/the-eth-zurich/education/ai-in-education/tools.html>. In particular, ETH offers Microsoft Copilot in this protected setup (note that this is not the same as GitHub Copilot).

If you have any more questions, don’t hesitate to contact me or stop by at the open lab hours (Q&A session) on Wednesday from 12-14h at LEE D101.

</details>

## Notes on Current Status

This report outlines the planned structure of the final report. At the same time, the example analyses included already reflect, to a large extent, the level of depth targeted in the final version.
As second assignment it provides an introduction to the project and summarizes secondary research on existing analyses of FC Barcelona’s set-pieces. From this review, key observations and research questions are derived, which can later be compared with our own analyses.
At this stage, the analysis focuses on relevant descriptive and general statistics, as well as FC Barcelona’s behaviour in offensive and defensive corners, in order to identify their underlying strategies.

## Introduction

This part introduces the analytical framework of our project and reviews existing tactical analyses of FC Barcelona's set pieces under Hansi Flick. 
It synthesises current literature on Barcelona's offensive and defensive corner behaviour, highlighting recurring attacking mechanisms, as well as defensive weaknesses related to hybrid marking structures. 
Based on these findings and qualitative match observations, the page then outlines the data-analysis plan for the project, with a particular focus on assessing Barcelona’s evolving set-piece strategy.

[Introduction, Review of Existing Analyses and Plan of Analysis](BAR-SP/introduction.md)

## Analysis of Overview Statistics

The purpose of this section is to provide an overview of FC Barcelona’s performance in the current UEFA Champions League season, identify broader tendencies in their use of set pieces within their tactical approach, and compare these patterns with those of their competitors.
It should be noted, however, that the sample size is small, and the conclusions we draw only apply to this tournament and do not support broader general conclusions.
We generate statistics for offensive and defensive set-pieces with the snippet $2765, using data from the league phase and round of 16.

[Overview on Set Piece Statistics of FC Barcelona](BAR-SP/statistics.md)

## Offensive Set-Pieces

This section presents the offensive set-piece analysis of FC Barcelona, with a particular focus on corners and free-kicks. 
It combines descriptive metrics, delivery characteristics, spatial patterns, and selected movement visualisations to identify the main principles of Barcelona’s attacking set-piece strategy.

#### Offensive Corners

[Offensive Corner Delivery Patterns](BAR-SP/offense.md#offensive-corners)

[Player Movement in Offensive Corners](BAR-SP/offense.md#movement-of-attacking-players)

## Defensive Set-Pieces

[Defensive XYZ](BAR-SP/defense.md)
