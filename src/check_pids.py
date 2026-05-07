import pandas as pd
from pathlib import Path
import zipfile
import json
import numpy as np
from mplsoccer import Pitch
from matplotlib import pyplot as plt
# Set up the base directory cleanly
DATA_DIR = Path(__file__).parent.parent / "data_new"
TEAM = "Barcelona"


def check_pids(game_id, pids):
    zip_path = DATA_DIR / "skillcorner" / f"{game_id}.zip"
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            json_filename = f"{game_id}.json"
            with zip_ref.open(json_filename) as json_file:
                # Read the file line by line
                data = json.load(json_file)
            id_to_name = {
                player['id']: player['short_name']
                for player in data.get('players', [])
            }


            return id_to_name

    except FileNotFoundError:
        print("fuck")


def get_pid_to_team_id(game_id):
    zip_path = DATA_DIR / "skillcorner" / f"{game_id}.zip"
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            with zip_ref.open(f"{game_id}.json") as json_file:
                data = json.load(json_file)
        return {
            player['id']: player['team_id']
            for player in data.get('players', [])
            if 'team_id' in player
        }
    except FileNotFoundError:
        print("fuck")


def check_pos_players(pos):
    for game_id, frame_dict in pos.items():
        pids = {entry['pid'] for frame_data in frame_dict.values() for entry in frame_data}
        id_to_name = check_pids(game_id, pids)
        if id_to_name is None:
            continue
        print(f"\nGame {game_id}:")
        for pid in pids:
            name = id_to_name.get(pid, f"<unknown id {pid}>")
            print(f"  {pid}: {name}")
