"""
DEMO 5 — Bot Detection
======================
A bot types with perfect, scripted timing (near-zero variance). The Cognitive
Cadence engine scores it as non-human; the Generative Honeypot engine
shadow-routes it instead of returning an error.

Run:  python examples/bot_detection_demo/demo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from examples import _simulation as sim
from examples._common import score_session


def show(label, result):
    print(f"  {label:<18} theta={result['theta']:.2f}  verdict={result['verdict']:<8} "
          f"shadow={result['shadow_mode']!s:<5} action={result['action_label']:<9} "
          f"mab_arm={result['mab_arm']}")


def main():
    print("=" * 72)
    print("DEMO 5 - BOT DETECTION  (Cognitive Cadence + Generative Honeypot)")
    print("=" * 72)

    human_timings = sim.human_keystroke_timings(seed=1)
    bot_timings = sim.bot_keystroke_timings()

    theta_human = sim.humanity_from_timings(human_timings)
    theta_bot = sim.humanity_from_timings(bot_timings)

    print(f"\nHuman keystroke variance (CV-derived) -> theta = {theta_human:.2f}")
    print(f"Bot   keystroke variance (CV-derived) -> theta = {theta_bot:.2f}  "
          "(scripted, ~0 variance)\n")

    human = score_session(theta_human, h_exp=0.8, latent=sim.human_latent("parik"))
    bot = score_session(theta_bot, h_exp=0.2, latent=sim.bot_latent())

    show("Legitimate human", human)
    show("Automated bot", bot)

    print("\nResult:")
    print(f"  - Human  -> served normally (preset={human['action_label']}).")
    if bot["shadow_mode"]:
        print(f"  - Bot    -> SHADOW-ROUTED into honeypot (MAB arm {bot['mab_arm']}); "
              "no real resource served.")
    else:
        print("  - Bot    -> NOT flagged (check thresholds / model weights).")
    print("\nThe bot is detected by *behavior*, not by a one-time challenge.")


if __name__ == "__main__":
    main()
