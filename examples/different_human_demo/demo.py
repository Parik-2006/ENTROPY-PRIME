"""
DEMO 3 — Different Human Detection
==================================
Parikshith enrolls. A friend then uses the SAME account on the SAME laptop and
browser. The Continuous-Auth engine detects the behavioral mismatch; trust
drops into the RED zone and re-authentication / logout is triggered.

Run:  python examples/different_human_demo/demo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from examples import _simulation as sim
from examples._common import continuous_check


def main():
    print("=" * 72)
    print("DEMO 3 - DIFFERENT HUMAN DETECTION  (same account / laptop / browser)")
    print("=" * 72)

    owner = "parik"
    baseline = sim.user_fingerprint(owner)
    print(f"\nEnrolled baseline for '{owner}'. Same session continues...\n")

    # The legitimate owner continues — recognized.
    owner_now = sim.human_latent(owner, day=2, stress=0.2)
    r_owner = continuous_check(owner_now, baseline, trust=1.0)
    print(f"  {owner} (account owner):   e_rec={r_owner['e_rec']:.3f}  "
          f"zone={r_owner['zone']}  action={r_owner['action']}")

    # A friend grabs the laptop mid-session — same account, different human.
    friend_now = sim.human_latent("friend_alex", day=0)
    r_friend = continuous_check(friend_now, baseline, trust=r_owner["trust_score"])
    print(f"  friend (same account):   e_rec={r_friend['e_rec']:.3f}  "
          f"zone={r_friend['zone']}  action={r_friend['action']}")

    print("\nResult:")
    print(f"  - Owner  -> {r_owner['zone']} (recognized).")
    print(f"  - Friend -> {r_friend['zone']} ({r_friend['action']}) - behavioral "
          "mismatch caught despite identical device/credentials.")


if __name__ == "__main__":
    main()
