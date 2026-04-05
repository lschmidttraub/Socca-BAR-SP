# How to use:
# Enter TEAM-Name (as in matches.csv), TEAM_SHORT_NAME and TEAM_UD(as in the game_id.json)
# get_all_player_positions_for_corners() returns dict, df of players positions (of all teams) for corners where TEAM is attacking
# df layout is game_id frame_id x y tid pid side direction where tid = team_id, pid = player_id direction in {ltr, rtl}
# side in {right/left} and coordinates transformed to STATSBOMB format (eg top left is 0,0)
# dict layout dict[game_id][frame_id] = [{'x':1, 'y':2, 'tid':264, 'pid':32411, 'side' = 'left', 'direction'='ltr'}, {...}, ...]
#
from pathlib import Path
from src.check_pids import get_pid_to_team_id


DATA_DIR = Path(__file__).parent.parent / "data_new"
TEAM = "Barcelona"
TEAM_SHORT_NAME = "FC Barcelona"
TEAM_ID = 264

import pandas as pd
from pathlib import Path
import zipfile
import json
import numpy as np
from mplsoccer import Pitch
from matplotlib import pyplot as plt



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


def extract_match_ids(team_name):
    file_path = DATA_DIR / "matches.csv"
    df = pd.read_csv(file_path)
    df_team = df[(df['home'] == team_name) | (df['away'] == team_name)]
    team_ids = [1 if x == team_name else 2 for x in df_team['home']]
    ids = df_team['skillcorner'].tolist()


    return ids, team_ids

def convert_coordinates(x,y, pitch_length, pitch_width):
    statsbomb_x = (x + (pitch_length / 2)) * (120.0 / pitch_length)
    statsbomb_y = ((pitch_width / 2) - y) * (80.0 / pitch_width)
    return statsbomb_x, statsbomb_y

def get_corners(game_ids, team_shname):
    corner_frames = { id:[] for id in game_ids }
    for id in game_ids:
        zip_path = DATA_DIR / "skillcorner" / f"{id}.zip"
        try:

            with zipfile.ZipFile(zip_path, "r") as zip_ref:

                with zip_ref.open(f"{id}_dynamic_events.csv") as csv_file:
                    df = pd.read_csv(csv_file)
                    #print(df.head(5))
                    frames = df[(df['game_interruption_before'] == 'corner_for') & (df['team_shortname'] == team_shname)]['frame_start']
                    frames = frames.tolist()
                    corner_frames[id] = frames

        except FileNotFoundError:
            print(f"Warning: Zip file not found at {zip_path}")
        except KeyError:
            print(f"Warning: {id}_dynamic_events.csv not found inside {id}.zip.")

    return corner_frames

def get_pitch_length(game_id):
    zip_path = DATA_DIR / "skillcorner" / f"{game_id}.zip"
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            json_filename = f"{game_id}.json"
            with zip_ref.open(json_filename) as json_file:


                data = json.load(json_file)
                pitch_length = data.get('pitch_length')
                pitch_widht = data.get('pitch_width')
                return pitch_length, pitch_widht
    except FileNotFoundError:
        print("fuck")
def get_tracking_for_frames(game_id, target_frame):

    extracted_data = []

    zip_path = DATA_DIR / "skillcorner" / f"{game_id}.zip"

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            jsonl_filename = f"{game_id}_tracking_extrapolated.jsonl"

            with zip_ref.open(jsonl_filename) as jsonl_file:


                for line in jsonl_file:
                    frame_data = json.loads(line.decode('utf-8'))
                    current_frame = frame_data.get('frame')


                    if current_frame == target_frame:
                        extracted_data = frame_data
                        break



    except FileNotFoundError:
        print(f"Warning: Zip file not found at {zip_path}")
    except KeyError:
        print(f"Warning: {jsonl_filename} not found inside {game_id}.zip")

    return extracted_data

def get_position_from_corners(corner_frames):
    pos = { id:{c:[] for c in corner_frames[id]} for id in corner_frames }
    for id in corner_frames.keys():
        pitch_length, pitch_widht = get_pitch_length(id)
        player_to_team = get_pid_to_team_id(id)
        for frame in corner_frames[id]:
            extracted_data = get_tracking_for_frames(id, frame)
            ball_data = extracted_data.get('ball_data') or {}
            ball_y_raw = ball_data.get('y', 0)
            ball_x_raw = ball_data.get('x', 0)
            # Skip frames where ball is not near the corner flag (y ≈ ±pitch_width/2)
            if abs(ball_y_raw) < pitch_widht * 0.25:
                continue
            direction = "ltr" if ball_x_raw > 0 else "rtl"
            player_list = extracted_data['player_data']
            max = -np.inf
            min = np.inf
            for p in player_list:
                max = np.maximum(max, p['y'])
                min = np.minimum(min, p['y'])
            if np.abs(max) > np.abs(min):
                corner_side = 'left' if direction == 'ltr' else 'right'
            else:
                corner_side = 'right' if direction == 'ltr' else 'left'
            for p in player_list:
                x = p['x']
                y = p['y']
                x,y = convert_coordinates(x,y, pitch_length, pitch_widht)
                tid = player_to_team[p['player_id']]
                pos_entry = {
                    'x' :x,
                    'y' :y,
                    'tid' :tid,
                    'pid' : p['player_id'],
                    'side': corner_side,
                    'direction': direction,
                }
                pos[id][frame].append(pos_entry)
    return pos


def create_map(positions, title, filename):
    df = pd.DataFrame(positions)
    df['y'] = np.where(df['direction']=='ltr', 80 - df['y'], df['y'])
    df['x'] = np.where(df['direction'] == 'ltr',  120 - df['x'], df['x'])
    df = df[df['tid'] == TEAM_ID]
    pitch = Pitch(
        pitch_type='statsbomb',
        pitch_color='#22312b',
        line_color='#c7d5cc'
    )
    fig, ax = pitch.draw(figsize=(10, 7))
    pitch.scatter(df['x'], df['y'], ax=ax, c='white', s=50, edgecolors='black', zorder=2)
    plt.title(title, color='white', fontsize=16)
    fig.set_facecolor('#22312b')
    fig_dir = Path(__file__).parent.parent / "assets" / filename
    plt.savefig(fig_dir)
    plt.show()

def get_all_player_positions_for_corners():
    ids, team_ids = extract_match_ids(TEAM)
    cs = get_corners(ids, TEAM_SHORT_NAME)
    pos = get_position_from_corners(cs)
    data = [
        {'game_id': game_id, 'frame_id': frame_id, **player_data}
        for game_id, frames in pos.items()
        for frame_id, player_list in frames.items()
        for player_data in player_list
    ]

    # 3. Create the DataFrame
    df = pd.DataFrame(data)
    return pos, df

pos, df = get_all_player_positions_for_corners()
print(df.head())
intermed = [value for frame_dict in pos.values() for value in frame_dict.values()]
positions = [item for sublist in intermed for item in sublist]

#player_ids = [pos['pid'] for pos in positions]
#positions = inner_val[:10]
print(positions)
#check_pos_players(pos)
for gid in list(pos.keys())[:2]:
    for frame in pos[gid].keys():
        print(pos[gid])
        positions = pos[gid][frame]
        if len(positions) == 0:
            continue
        print(positions)
        create_map(positions,  f"Player Positions – Corner in {gid} at Frame {frame}",  f"corner_heatmap_individual_{gid}_{frame}")


