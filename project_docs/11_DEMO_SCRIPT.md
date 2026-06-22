# Entropy Prime — Live Demonstration Script

**Duration:** ~8–10 minutes. **Team roles:** the script assigns a speaker per
segment — adapt names to your team (Speaker A/B/C/D).

**Pre-flight (before the audience):**
- Backend running on `:8000` (current code — confirm the startup log shows
  `✓ Deception shadow API mounted` and `[RouteAudit] /admin/deception/* PRESENT`).
- Frontend running: `npm run dev` → open `http://localhost:3001/?dev=1`
  (the `?dev=1` flag shows the Identity Debug panel).
- Optional: MongoDB + Redis running for durable persistence.
- Two people available to type (the "owner" and an "impostor").

---

## Segment 1 — Login & Enrolment  *(Speaker A)*
**Do:** Log in with the demo account. Begin enrolment by typing the prompts.
**Say:** "Authentication starts with a normal password — hashed with Argon2id —
but Entropy Prime then *learns how you type*. As I type, it captures dwell,
flight and per-digraph timing and freezes an enrolment template."
**Show:** The Identity Debug panel reports `Frozen template captured`.

## Segment 2 — Trusted Dashboard  *(Speaker A)*
**Do:** Land on the dashboard and keep typing/moving normally.
**Say:** "Notice the identity confidence stays in the Trusted zone, 80–100. This
is continuous — it re-checks every couple of seconds, and it freezes when I'm
idle, so leaving the screen never triggers a false alarm."
**Show:** Confidence ~90–100, zone Trusted; go idle for ~10 s to show it holds.

## Segment 3 — Impostor Detection  *(Speaker B types as the "impostor")*
**Do:** A different person types in a text field for ~10–15 seconds.
**Say:** "Same account, same session, correct password — but a *different person*
is now typing. Watch the confidence decay gradually as the typing and digraph
similarity fall."
**Show:** Confidence eases down (e.g. 95→82→70→…), enters Monitor, then on a
sustained mismatch drops below 60 and the **re-authentication modal** appears.
**Say:** "It only challenges on a *sustained* mismatch — never on a single odd
keystroke."

## Segment 4 — Verify & Recover  *(Speaker A)*
**Do:** Click *Verify Identity* (or re-login) as the owner.
**Say:** "After verification, trust resets cleanly and a cooldown starts, so it
won't immediately re-prompt."
**Show:** Confidence returns to Trusted; no loop.

## Segment 5 — Deception Demo Lab: Credential Stuffing  *(Speaker C)*
**Do:** Navigate to **Entropy Prime → Deception Demo Lab**. Select **Credential
Stuffing** and click **Launch Simulation**.
**Say:** "Now the offensive side. Instead of *blocking* attackers, we *deceive*
them. This launches a real credential-stuffing pattern through the live
classifier."
**Show:** The six-stage **Attack Pipeline** animates: Attack Detected →
Classification (`credential_stuffing`) → Risk Assessment → Honeypot Selection →
Shadow Environment (Banking Shadow World) → Monitoring.

## Segment 6 — Attacker View: Banking Shadow World  *(Speaker C)*
**Do:** Switch to the **Attacker View** tab.
**Say:** "From the attacker's side, the login *succeeded* — they see a complete,
believable banking application: accounts, transactions, beneficiaries,
statements. None of it is real; it's seeded synthetic data, fully isolated."
**Show:** Browse the synthetic banking tabs and paginated transactions.

## Segment 7 — Reconnaissance → Shadow Admin  *(Speaker D)*
**Do:** Launch the **Reconnaissance** simulation.
**Say:** "A reconnaissance attacker probing for admin endpoints is routed to a
Shadow Admin console — the highest-value bait."
**Show:** Attack Pipeline routes to Shadow Admin World; in the Attacker View open
the **API Keys** page.
**Say:** "These secrets are *canary tokens* — fake but trackable. If an attacker
exfiltrates and uses one, we get a high-fidelity alert."

## Segment 8 — Other Vectors (optional, quick)  *(Speaker D)*
**Do:** Quickly launch Data Scraper, Brute Force, Session Hijacking.
**Say:** "Each intent maps to a tailored environment — a synthetic dataset for
scrapers, a tarpit for brute force, a restricted sandbox for session abuse."

## Segment 9 — Conclusion  *(Speaker A)*
**Say:** "To summarise: Entropy Prime makes authentication *continuous* — it
notices when a different person takes over — and it makes threat response
*deceptive* — attackers think they won while they're isolated in a fake world
and we watch. We keep the right user in, and keep attackers busy somewhere that
isn't real."
**Show:** Return to the dashboard (Trusted) to close.

---

**Fallback tips:** If the shadow environment can't reach the backend, a
believable banking *maintenance screen* is shown instead of an error (no
disclosure). If the backend was restarted mid-demo, simply re-login (sessions
are in-memory under mongomock).
