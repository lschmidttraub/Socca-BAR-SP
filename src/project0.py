import json 
from pathlib import Path

folder = Path(r"C:\Users\danch\Desktop\soca\league_phase")

for lineup_file in folder.glob("*_lineups.json"):
    base_name = lineup_file.stem.replace("_lineups", "")
    event_file = folder / f"{base_name}.json"

    with open(lineup_file, encoding="utf-8") as f:
        lineup = json.load(f)
    
    barcelona_playing = False
    opponent_team = ""
    for team in lineup:
        barcelona_playing |= team["team_name"] == "Barcelona"
        if team["team_name"] != "Barcelona": opponent_team = team["team_name"]

    if not barcelona_playing: continue



    with open(event_file, encoding="utf-8") as f:
        game = json.load(f)
    
    passes_barcelona = 0
    goals_barcelona = 0
    for event in game:
        if event["type"]["id"] == 30 and event["team"]["name"] == "Barcelona":
            passes_barcelona += 1
        if event["type"]["id"] == 16 and event["shot"]["outcome"]["id"] == 97 and event["team"]["name"] == "Barcelona":
            goals_barcelona += 1

    print("In the game against " + str(opponent_team) + ", Barcelona did " + str(passes_barcelona) + " passes and " + str(goals_barcelona) + " goals. Used file: " + str(base_name)+".json")