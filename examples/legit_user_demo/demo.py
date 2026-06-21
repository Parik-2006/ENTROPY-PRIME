"""
DEMO 2 — Legitimate User Recognition
====================================
Parikshith enrolls (a behavioral baseline is stored). Over several days he logs
in again. The Continuous-Auth engine recognizes him; trust stays high (GREEN).

Run:  python examples/legit_user_demo/demo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from examples import _simulation as sim
from examples._common import continuous_check


def main():
    print("=" * 72)
    print("DEMO 2 - LEGITIMATE USER RECOGNITION  (Continuous Authentication)")
    print("=" * 72)

    user = "parik"
    baseline = sim.user_fingerprint(user)   # stored at enrollment
    print(f"\nEnrolled behavioral baseline for '{user}'.\n")

    print(f"  {'session':<18}{'e_rec':>8}{'zone':>8}{'trust':>8}   action")
    all_green = True
    for day in range(1, 6):
        stress = 0.1 * day                  # mild day-to-day variation
        current = sim.human_latent(user, day=day, stress=stress)
        r = continuous_check(current, baseline, trust=1.0)
        all_green = all_green and r["zone"] == "GREEN"
        print(f"  day {day} login      {r['e_rec']:>8}{r['zone']:>8}"
              f"{r['trust_score']:>8}   {r['action']}")

    print("\nResult:", "[OK] recognized every day - trust stayed HIGH (GREEN)."
          if all_green else "[!] unexpected drift; inspect thresholds.")


if __name__ == "__main__":
    main()
