"""
DEMO 1 — CAPTCHA Bypass
=======================
Shows why a one-time CAPTCHA is insufficient. A bot (Selenium/Puppeteer/Buster
/ human-solver farm) *passes* the CAPTCHA, then proceeds with automated
behavior. A traditional gate lets it in. Entropy Prime evaluates behavior
continuously and shadow-routes it anyway.

Run:  python examples/captcha_bypass_demo/demo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from examples import _simulation as sim
from examples._common import score_session


def traditional_gate(captcha_passed: bool) -> str:
    """The status quo: trust a one-time challenge."""
    return "ALLOW (full access)" if captcha_passed else "BLOCK"


def entropy_prime_gate(theta: float, latent) -> dict:
    """Behavior-based: ignore the one-time challenge, judge the actor."""
    return score_session(theta, h_exp=0.3, latent=latent)


def main():
    print("=" * 72)
    print("DEMO 1 - CAPTCHA BYPASS  (why one-time challenges fail)")
    print("=" * 72)

    # A bot solved the CAPTCHA (via automation or a human-solver service).
    captcha_passed = True
    bot_theta = sim.humanity_from_timings(sim.bot_keystroke_timings())
    bot_latent = sim.bot_latent()

    print(f"\nScenario: automated bot, captcha_passed = {captcha_passed}, "
          f"behavioral theta = {bot_theta:.2f}\n")

    print("Traditional CAPTCHA-only gate:")
    print(f"  decision -> {traditional_gate(captcha_passed)}")
    print("  => The bot is now INSIDE. CAPTCHA verified a moment, not the actor.\n")

    print("Entropy Prime behavioral gate:")
    ep = entropy_prime_gate(bot_theta, bot_latent)
    decision = "SHADOW-ROUTED to honeypot" if ep["shadow_mode"] else f"allow ({ep['action_label']})"
    print(f"  verdict={ep['verdict']}  shadow_mode={ep['shadow_mode']}  decision -> {decision}")
    print("  => The bot is caught despite passing the CAPTCHA.\n")

    # Contrast: a real human who also passed the CAPTCHA is served normally.
    human_theta = sim.humanity_from_timings(sim.human_keystroke_timings())
    human = entropy_prime_gate(human_theta, sim.human_latent("parik"))
    print(f"Control (real human, theta={human_theta:.2f}): "
          f"shadow_mode={human['shadow_mode']} -> served normally "
          f"(preset={human['action_label']}).")


if __name__ == "__main__":
    main()
