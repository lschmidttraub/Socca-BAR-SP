import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from mplsoccer import Pitch

# Reuse the project's StatsBomb zip loader and matches helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent / "corners"))
from defending_corners import (  # noqa: E402
    BARCELONA,
    ASSETS_DIR,
    read_statsbomb,
    team_games,
)

# -----------------------
# CONFIG
# -----------------------
team_target = BARCELONA
output_folder = ASSETS_DIR / "defense" / "free_kicks"
output_folder.mkdir(parents=True, exist_ok=True)

plt.rcParams['figure.dpi'] = 120
sns.set_theme(style="whitegrid")


# -----------------------
# MAIN ANALYSIS
# -----------------------
def run_full_defense_analysis() -> pd.DataFrame:
    results = []

    for game_id in team_games(team_target):
        try:
            events = read_statsbomb(game_id)
        except FileNotFoundError:
            print(f"Missing statsbomb file for game {game_id}, skipping.")
            continue

        df = pd.json_normalize(events, sep='.')
        if 'type.name' not in df.columns:
            continue

        mask = (
            (df['type.name'] == 'Shot')
            & (df['team.name'] != team_target)
            & (df.get('play_pattern.name') == 'From Free Kick')
        )
        fks_against = df[mask]

        for idx, shot in fks_against.iterrows():
            pos_id = shot.get('possession')
            if pd.isna(pos_id):
                continue
            pos_events = df[(df['possession'] == pos_id) & (df.index <= idx)]
            if pos_events.empty:
                continue

            origin_loc = df.at[pos_events.index[0], 'location']
            if not isinstance(origin_loc, list) or len(origin_loc) < 2:
                continue

            # Only fouls/restarts in Barcelona's defensive half
            if origin_loc[0] <= 60:
                continue

            obv = shot.get('statsbomb_obv.value')
            if pd.isna(obv):
                obv = shot.get('shot.statsbomb_xg')
            if pd.isna(obv):
                obv = 0.0

            results.append({
                'system': 'Zonal-Marking',
                'obv_against': float(obv),
                'x': origin_loc[0],
                'y': origin_loc[1],
            })

    return pd.DataFrame(results)


# -----------------------
# EXECUTION & PLOTTING
# -----------------------
df_res = run_full_defense_analysis()

if not df_res.empty:
    all_systems = ['Zonal-Marking', 'Man-Marking']
    df_res['system'] = pd.Categorical(df_res['system'], categories=all_systems)

    # --- PLOT 1: Heatmap ---
    fig, ax = plt.subplots(figsize=(10, 7))
    pitch = Pitch(pitch_type='statsbomb', pitch_color='white', line_color='#222222')
    pitch.draw(ax=ax)
    ax.set_xlim(60, 120)

    stats = pitch.bin_statistic(
        df_res.x, df_res.y, values=df_res.obv_against,
        statistic='mean', bins=(12, 8),
    )
    pcm = pitch.heatmap(stats, ax=ax, cmap='Reds', edgecolors='none', alpha=0.8)

    plt.colorbar(pcm, ax=ax, label='Danger (Mean OBV/xG)')
    plt.title(f"Danger by Foul Location: Free Kicks against {team_target}")
    plt.savefig(output_folder / "1_fk_heatmap.png", bbox_inches='tight')
    plt.close(fig)

    # --- PLOT 2: System Efficiency ---
    fig2 = plt.figure(figsize=(8, 6))
    sns.boxplot(
        data=df_res, x='system', y='obv_against',
        color='#d9adad', hue='system', legend=False,
    )
    plt.title("Defensive Efficiency (System Comparison)")
    plt.ylabel("Danger (OBV/xG)")
    plt.xlabel("System")
    plt.savefig(output_folder / "2_system_efficiency.png", bbox_inches='tight')
    plt.close(fig2)

    print(f"Analysis complete. {len(df_res)} scenarios processed.")
    print(f"Plots written to: {output_folder}")
else:
    print("No data found for analysis.")
