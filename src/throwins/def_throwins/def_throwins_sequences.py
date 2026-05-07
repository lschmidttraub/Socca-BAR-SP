"""
def_throwins_sequences.py

Full-pitch scatter of opponent throw-in sequences where Barcelona did not win the ball back.
Orange dot = throw-in origin · Red arrows = sequence through the pitch.

Usage:
    python src/throwins/def_throwins/def_throwins_sequences.py
"""

from throwins_defense import (
    collect_lost_sequences,
    plot_lost_sequences,
)

MAX_SECONDS = 6.0

if __name__ == "__main__":
    chains = collect_lost_sequences(max_seconds=MAX_SECONDS)
    print(f"\nSequences where Barça did not win ball back: {len(chains)}")
    plot_lost_sequences(chains, max_seconds=MAX_SECONDS)
