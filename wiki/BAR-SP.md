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

**Disclaimer:** Generative AI was used to generate the plots in this report.

**Current status:** This report is not final, and will be updated as we progress. It does however outline the planned structure of the final report, and the example analyses included already reflect, to a large extent, the level of depth targeted in the final version. To keep a clean commit history, we do most of our work in a public repository, which can be found [here](https://github.com/lschmidttraub/Socca-BAR-SP).

## Introduction

FC Barcelona have traditionally been associated with a highly technical style of play, based on positional structure and collective ball control. 
For many years, analyses of Barcelona focused primarily on their behaviour in open play rather than on set-pieces (apart from Alexander-Arnold's infamous corner in Liverpool's 2019 4-0 comeback).
However, this framing has become less adequate since Hansi Flick’s appointment as manager in July 2024. 
Analyses show that Barcelona’s game has become more direct, more vertical and more aggressive in attacking dangerous spaces across all phases of play, including set-piece situations. (See [Coaches' Voice 2025](https://learning.coachesvoice.com/cv/hansi-flick-tactics-barcelona/))

Reports from the Flick era already suggest that dead-ball situations, and corners in partiular, have represented both a competitive strength and a vulnerability for Barcelona.
Existing analyses repeatedly identify corners as the phase in which Barcelona’s tactical ideas are most clearly visible &mdash; both offensively, through coordinated and vertical routines, and defensively, through recurring issues in marking and far-post protection.
Analysing corners of the CL 25/26 thus provides a strong entry point for understanding how Barcelona currently use set pieces and how their usage has evolved since last season.
We further review the prominent findings of previous analyses [here](BAR-SP/previous-analyses).

## Plan of the Report

To address the scarcity of the data available to us, we balance statistical analyses with qualitative reviews of indivual matches and plays: we start our report with a statistical overview of Barcelona's set piece performance, comparing it to other clubs, followed by more in-depth analyses specific to Barcelona's strategy.
Our subsequent analyses can be broadly divided into offensive and defensive categories. As mentioned in the introduction, we place particular emphasis on corners, as our qualitative review of Barcelona's game suggests that they are especially crucial to Barcelona’s offensive and defensive set-piece strategy.

The data used throughout these analyses is drawn from the league phase and round of 16 of the current UEFA Champions League season.
We stress that due to the small sample size, the conclusions we draw only apply to this tournament and do not necessarily support more general conclusions.


### [Overview of Set Piece Statistics](BAR-SP/statistics)

In this section, we provide an overview of FC Barcelona’s performance in the current UEFA Champions League season, identify broader tendencies in their use of set pieces within their tactical approach, and compare these patterns with those of their competitors.
We generate the charts and tables in this section with the snippet $2765.
The analysis is divided into [offensive](BAR-SP/statistics#offensive-set-pieces) and [defensive](BAR-SP/statistics#defensive-set-pieces) set-pieces.


### [Offensive Set-Pieces](BAR-SP/offense)

This section presents the offensive set-piece analysis of FC Barcelona, with a particular focus on corners and free-kicks. 
It combines descriptive metrics, delivery characteristics, spatial patterns, and selected movement visualisations to identify the main principles of Barcelona’s attacking set-piece strategy.

#### [Offensive Corners](BAR-SP/offense#offensive-corners)
We start by investigating  [Offensive Corner Delivery Patterns](BAR-SP/offense#offensive-corners), followed by a discussion of [Player Movement in Offensive Corners](BAR-SP/offense#movement-of-attacking-players).

### [Defensive Set-Pieces](BAR-SP/defense)
