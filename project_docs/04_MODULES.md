# Entropy Prime — Modules

Each module is described by **Purpose · Inputs · Outputs · Workflow**.

---

## 1. Behavioral Biometrics

**Purpose.** Capture and quantify how a user types and moves, producing a stable
per-user behavioural signature.

**Inputs.** Raw `keydown`/`keyup` and `mousemove`/`touchmove` events from the
browser.

**Outputs.** An 8-dimensional normalised feature vector (dwell, flight, pointer
speed, jitter, acceleration, rhythm, pause, bigram ratio); a per-digraph latency
map; and a frozen `EnrollmentTemplate` (dwell/flight mean+std, digraph
latencies, mouse means).

**Workflow.** Collectors buffer timestamped events → `buildFeatureVector()` and
`buildCNNInput()` derive features → on the first ~30 keystrokes an immutable
enrolment template is captured and persisted (per user) → subsequently the live
signature is scored against this frozen template.

---

## 2. Continuous Authentication

**Purpose.** Continuously verify that the operator is still the enrolled user and
challenge for re-verification only on a sustained mismatch.

**Inputs.** Live feature vectors, the frozen enrolment template, and the session
token.

**Outputs.** A progressive identity score (0–100), an effective trust value, and
a zone (Trusted 80–100 / Monitor 60–79 / Re-auth 0–59); a 30-second server
heartbeat to `/session/verify`.

**Workflow.** Every 1.5 s `computeIdentity()` produces a continuous score from
typing (40%), digraph (40%) and mouse (20%) similarity; a rolling 20-sample
window and suspicion accumulator gate re-auth so it fires only on a sustained
sub-60 pattern; corroboration (strong digraph+mouse) suppresses re-auth; idle
periods freeze the score; after a verify a cooldown prevents immediate
re-prompts. The score drives `trustScore` → confidence → re-auth modal.

---

## 3. Attack Classification

**Purpose.** Infer attacker intent so the deception engine can choose an
appropriate strategy.

**Inputs.** `AttackSignals` — distinct usernames, failed/password attempts,
request rate, admin-path hits, unique paths, 404 ratio, humanity θ, user-agent.

**Outputs.** An `AttackClassification` — class (CREDENTIAL_STUFFING, BRUTE_FORCE,
RECON, SCRAPER, UNKNOWN), confidence band, reasons, suggested world, arm hint.

**Workflow.** Deterministic, explainable rules evaluated in precedence order
(recon → credential stuffing → brute force → scraper → unknown). Runs server-side
inside `/score` when a request is shadow-routed.

---

## 4. Honeypot Routing

**Purpose.** Decide whether a request is shadow-routed and mint a believable
"success" without disclosing detection.

**Inputs.** The Stage-1 biometric verdict/confidence, classifier output, shadow
secret, client IP.

**Outputs.** A `should_shadow` decision, a normal-format session token (no
attacker-detectable prefix), an MAB deception arm, and a signed challenge.

**Workflow.** `_should_shadow()` gates routing (BOT always; SUSPECT only at
high/medium confidence). On shadow, the Synthetic Success Injector registers a
server-side shadow state keyed by the token and returns a normal success
envelope with a redirect.

---

## 5. Shadow Banking Environment

**Purpose.** Present a believable retail-banking application to a shadow-routed
attacker.

**Inputs.** The shadow session token and a deterministic per-session world seed.

**Outputs.** Synthetic JSON for dashboard, accounts, transactions (paginated),
beneficiaries, statements and customer profile.

**Workflow.** `BankingProfile` generates seeded, self-consistent data (same seed
→ same world; different seed → a different but equally plausible bank). Served at
`/api/shadow/*` and rendered by `ShadowEnvView`.

---

## 6. Shadow Admin Environment

**Purpose.** Present a believable admin console to reconnaissance attackers — the
highest-value, most heavily instrumented bait.

**Inputs.** The shadow session token and world seed.

**Outputs.** Synthetic users, audit logs, analytics, configuration and **canary
API keys**.

**Workflow.** `ShadowAdminProfile` generates the admin surface at
`/api/shadow/admin/*`; exposed "secrets" are tracked honeytokens whose later use
is a high-fidelity exploitation signal.

---

## 7. Deception Demo Lab

**Purpose.** A presentation surface that drives the *real* pipeline and visualises
it.

**Inputs.** A selected attack vector (5 options).

**Outputs.** A live `/score` classification, an animated six-stage attack
pipeline, and the rendered attacker environment.

**Workflow.** `simulateAttack()` posts bot-like signals to `/score`; the response
drives the `AttackPipeline` animation (Attack Detected → Classification → Risk
Assessment → Honeypot Selection → Shadow Environment → Monitoring) and the
`ShadowEnvView` renders the attacker's synthetic world from `/api/shadow/*`.

---

## 8. Monitoring Layer

**Purpose.** Record shadow-session activity as threat intelligence.

**Inputs.** Shadow-session lifecycle events (start, page visit, API call, canary
hit).

**Outputs.** In-process session/event summaries and best-effort MongoDB records
(`shadow_sessions`, `attacker_events`).

**Workflow.** `ThreatIntelRecorder` maintains a thread-safe in-process store
(always available) and mirrors to MongoDB when reachable; the recorded data
underpins the conceptual "Monitoring" stage of the attack pipeline.
