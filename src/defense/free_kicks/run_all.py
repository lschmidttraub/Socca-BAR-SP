"""
run_all.py

Runs every defensive free-kick analysis in this folder and saves all
plots to ``assets/def_fk_analysis/``.

Usage:
    python src/defense/free_kicks/run_all.py
"""

import matplotlib

# Use a non-interactive backend so plt.show() inside each script does
# not block when run in batch.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import def_fk_outcomes
import def_fk_delivery_map
import def_fk_first_touch
import def_fk_direct_shots
import def_fk_runs


SCRIPTS = [
    ("Outcome distribution",        def_fk_outcomes.run),
    ("Delivery origin → endpoint",  def_fk_delivery_map.run),
    ("First touch after delivery",  def_fk_first_touch.run),
    ("Direct FK shots conceded",    def_fk_direct_shots.run),
    ("Per-FK possession runs",      def_fk_runs.run),
]


def main() -> None:
    for name, runner in SCRIPTS:
        print(f"\n=== {name} ===")
        runner()
        plt.close("all")
    print("\nAll defensive FK analyses complete.")


if __name__ == "__main__":
    main()
