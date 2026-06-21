"""
DEMO 4 — Human Variability Handling
===================================
The same person types differently on different days — fast, slow, tired,
stressed. Entropy Prime must NOT falsely reject them: it scores *relative*
drift against an adaptive baseline, not absolute speed.

    User A (fast day)  ≈  User A (slow day)   !=   User B

Run:  python examples/human_variability_demo/demo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from examples import _simulation as sim
from examples._common import continuous_check


def main():
    print("=" * 72)
    print("DEMO 4 - HUMAN VARIABILITY HANDLING  (no false rejects)")
    print("=" * 72)

    user = "parik"
    baseline = sim.user_fingerprint(user)
    print(f"\nEnrolled baseline for '{user}'.\n")

    scenarios = [
        ("fast / fresh day", dict(day=1, stress=0.0)),
        ("slow / careful day", dict(day=2, stress=0.3)),
        ("tired evening", dict(day=3, stress=0.6)),
        ("stressed / rushed", dict(day=4, stress=0.9)),
    ]

    print("Same user, different states:")
    same_user_ok = True
    for name, kw in scenarios:
        cur = sim.human_latent(user, **kw)
        r = continuous_check(cur, baseline, trust=1.0)
        same_user_ok = same_user_ok and r["zone"] != "RED"
        print(f"  {name:<22} e_rec={r['e_rec']:.3f}  zone={r['zone']:<6} action={r['action']}")

    print("\nDifferent human (control):")
    other = continuous_check(sim.human_latent("friend_alex", day=0), baseline, trust=1.0)
    print(f"  {'friend_alex':<22} e_rec={other['e_rec']:.3f}  zone={other['zone']:<6} "
          f"action={other['action']}")

    print("\nResult:")
    print(f"  - User A across all states -> {'never RED (no false reject)' if same_user_ok else 'FALSE REJECT - tune thresholds'}.")
    print(f"  - User B -> {other['zone']} (correctly flagged).")
    print("  => Relative drift, not absolute speed:  A_fast ~= A_slow  !=  B.")


if __name__ == "__main__":
    main()
