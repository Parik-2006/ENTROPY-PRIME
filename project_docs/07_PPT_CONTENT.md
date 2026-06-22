# Entropy Prime — Presentation Slide Deck (12–15 slides)

Each slide: **Content · Diagram suggestion · Speaker notes.**

---

### Slide 1 — Title
**Content:** "Entropy Prime — Continuous Behavioural Authentication & Generative
Deception." Team names, guide, institution, date.
**Diagram:** Project logo / shield motif.
**Speaker notes:** One sentence: "We make authentication continuous and turn
attacks into deception instead of blocks."

### Slide 2 — The Problem
**Content:** Login verifies identity *once*; stolen credentials and session
hijacking go unnoticed; blocking attackers discloses the defence.
**Diagram:** "Login ✓ → trusted forever" timeline with a red intruder midway.
**Speaker notes:** Stress the single-point-of-trust weakness and the
detection-equals-disclosure problem.

### Slide 3 — Existing Limitations
**Content:** Binary auth, no behavioural continuity, blocking leaks the defence,
no intelligence capture, one-size threat response.
**Diagram:** Comparison table (Traditional vs Entropy Prime).
**Speaker notes:** Frame these as the gaps the project addresses.

### Slide 4 — Our Solution (Overview)
**Content:** Two cooperating capabilities — Continuous Behavioural Auth +
Generative Deception.
**Diagram:** Two-pillar diagram.
**Speaker notes:** "One keeps the right user in; the other keeps attackers busy
in a fake world."

### Slide 5 — System Architecture
**Content:** User → Behavioral Engine → Identity Verification → Attack
Classification → Deception Engine → Shadow Environment → Monitoring.
**Diagram:** Architecture flow (from `03_SYSTEM_ARCHITECTURE.md`).
**Speaker notes:** Walk top-to-bottom once.

### Slide 6 — Behavioural Biometrics
**Content:** 8-D keystroke/pointer features; per-digraph latency; frozen
enrolment template.
**Diagram:** Feature breakdown + "owner vs impostor" bar chart.
**Speaker notes:** Emphasise digraph latency as the strong per-person signal.

### Slide 7 — Continuous Authentication & Zones
**Content:** Progressive score; Trusted 80–100 / Monitor 60–79 / Re-auth 0–59;
idle-freeze, corroboration, cooldown.
**Diagram:** Gradual decay line "98→90→82→…→58" with zone bands.
**Speaker notes:** "We re-authenticate only on a *sustained* mismatch — no
second-to-second prompts."

### Slide 8 — Impostor Detection Demo (Live)
**Content:** Owner types → 90–100; different person types → drops below 60 →
re-auth modal.
**Diagram:** Screenshot of the identity debug panel.
**Speaker notes:** This is the headline live demo; narrate the score dropping.

### Slide 9 — Generative Deception
**Content:** Synthetic Success Injection — detection never equals disclosure;
attacker "logs in" and is isolated.
**Diagram:** "Bot detected → status: success → shadow world."
**Speaker notes:** Contrast with blocking/CAPTCHA.

### Slide 10 — Attack Classification & Routing
**Content:** Five intents → five environments (banking, admin, dataset, tarpit,
restricted sandbox).
**Diagram:** Mapping table.
**Speaker notes:** Mention rules are transparent and auditable.

### Slide 11 — Shadow Environments (Live)
**Content:** Believable banking app and admin console with canary secrets.
**Diagram:** Screenshots of Banking Shadow World and Shadow Admin.
**Speaker notes:** Point out the canary API keys as attribution bait.

### Slide 12 — Deception Demo Lab & Pipeline
**Content:** Six-stage animated pipeline driven by the real backend.
**Diagram:** Screenshot of the Attack Pipeline animation.
**Speaker notes:** "Every value here comes from the live classifier and routing."

### Slide 13 — Technology Stack
**Content:** React/Vite, FastAPI/Python, MongoDB/Redis, Argon2id, Docker, TF.js.
**Diagram:** Layered stack icons.
**Speaker notes:** Note graceful in-memory fallbacks.

### Slide 14 — Results & Status
**Content:** Working: biometrics, continuous auth, classification, routing,
shadow worlds, demo lab. Partial: durable persistence (needs MongoDB).
**Diagram:** Status matrix (from `FINAL_AUDIT.md`).
**Speaker notes:** Be honest about partial items.

### Slide 15 — Conclusion & Future Work
**Content:** Continuous + deceptive defence shifts the asymmetry to the defender.
Future: ML classifier, contextual-bandit selection, canary attribution at scale.
**Diagram:** Roadmap timeline.
**Speaker notes:** End with the one-line thesis from Slide 1.
