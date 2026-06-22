# Entropy Prime — Viva Preparation (50 Q&A)

## Behavioural Biometrics

**1. What behavioural signals does the system capture?**
Keystroke dynamics (key hold/dwell time, inter-key flight time, per-digraph
latency, typing rhythm, pauses) and pointer dynamics (speed, jitter,
acceleration).

**2. What is dwell time vs flight time?**
Dwell is how long a key is held (keydown→keyup); flight is the gap between
releasing one key and pressing the next. Both are person-specific.

**3. What is a digraph latency and why is it important?**
The timing signature of a specific two-key sequence (e.g. "th"). It is highly
person-specific and is weighted heavily (40%) because it discriminates different
humans far better than average speed.

**4. How many features are in the behavioural vector?**
Eight: dwell, flight, pointer speed, jitter, acceleration, rhythm, pause, and
bigram ratio — each normalised to [0,1].

**5. What is the enrolment template and why is it frozen?**
An immutable snapshot of the owner's typing signature (dwell/flight mean+std,
digraph latencies, mouse means) captured once. It is frozen so an impostor's
input can never be absorbed into the baseline.

**6. How is the identity score computed?**
A weighted similarity: 40% typing + 40% digraph + 20% mouse, each a Gaussian
similarity of the live value's relative difference from the template, combined
into a 0–100 score.

**7. Why weight mouse low?**
Mouse dynamics are noisy and weakly person-specific; weighting them high would
let a matching mouse mask a typing mismatch.

**8. How do you tell a different *human* (not just a bot)?**
By comparing fine-grained typing/digraph timing to the frozen template; a
different human has a different signature even at similar speeds.

**9. What stops average typing speed from being the only signal?**
The same user types faster/slower by context, so speed alone is unreliable;
digraph latency and distribution shape carry the discriminative signal.

**10. Where does behavioural modelling run?**
In the browser using TensorFlow.js (1-D CNN humanity scorer and an autoencoder
for drift), plus a pure-JS identity scorer.

## Continuous Authentication

**11. What does "continuous authentication" mean here?**
Identity is re-evaluated continuously (every ~1.5 s live, every 30 s server
heartbeat), not just at login.

**12. What are the confidence zones?**
Trusted 80–100, Monitor 60–79, Re-authenticate 0–59.

**13. When does the re-auth modal appear?**
Only when confidence falls below 60 on a *sustained* mismatch; Monitor never
opens the modal.

**14. How do you avoid false re-auth prompts?**
A suspicion accumulator over a rolling 20-sample window, hysteresis (sustained
sub-60 required), corroboration override, idle-freeze, and a post-verify
cooldown.

**15. What is the corroboration override?**
If digraph similarity > 0.80 and mouse similarity > 0.75, the session is treated
as the owner in a different context and is never escalated to re-auth.

**16. How are idle periods handled?**
If no keyboard/pointer event occurs within 5 s, evaluation is skipped: the score,
drift and suspicion freeze, and no re-auth can fire.

**17. What happens after a successful verify?**
Trust resets to 1.0, identity score to 100, suspicion to 0, anomaly cleared, and
a 90-second cooldown starts so the modal cannot immediately reappear.

**18. What is the post-verify cooldown for?**
To prevent an immediate re-auth loop right after the user verifies.

**19. How does the score decay — gradually or instantly?**
Gradually, via EMA smoothing (e.g. 98→90→82→74→66→58), so it is progressive, not
binary.

**20. How does the heartbeat authenticate to the server?**
By sending the session token in the `X-Session-Token` header to
`/session/verify`.

## FastAPI / Backend

**21. Why FastAPI?**
Async performance, automatic validation via Pydantic, typed contracts, and
built-in OpenAPI docs.

**22. What does `/score` do?**
Runs the four-stage pipeline; for malicious traffic it classifies intent,
registers a shadow session, and returns a believable success with a redirect.

**23. What are the four pipeline stages?**
Stage 1 Biometric (humanity verdict), Stage 2 Honeypot (shadow routing + MAB
arm), Stage 3 Governor (Argon2id preset), Stage 4 Watchdog (continuous drift).

**24. How is a session validated on the server?**
A dependency (`_SessionGuardDep`) reads `X-Session-Token`, looks the session up
(Redis cache then MongoDB), and returns 401 if absent/expired.

**25. How is the deception API mounted?**
As an additive FastAPI router (`framework.deception.api`) included in `main.py`,
exposing `/api/shadow/*`.

**26. How does the backend behave if MongoDB is down?**
It falls back to an in-memory `mongomock-motor` client, so the server still
starts and the demo functions (without durable persistence).

**27. How are validation errors surfaced?**
Pydantic models validate request bodies; FastAPI returns structured 422 errors,
which the frontend formats.

**28. What is the lifespan function?**
An async context manager that connects Mongo/Redis, loads checkpoints, builds the
orchestrator on startup and cleans up on shutdown.

## MongoDB

**29. Why MongoDB?**
A flexible document model suits evolving security records (sessions, profiles,
shadow sessions, events) without rigid schemas.

**30. Which collections are used?**
`users`, `sessions`, `biometric_profiles`, `honeypot`, `shadow_sessions`,
`attacker_events`.

**31. How are sessions expired?**
Each session document has an `expires_at` (30-minute TTL); expired sessions are
rejected and swept.

**32. What driver is used?**
`motor` (async MongoDB driver), with `mongomock-motor` as the in-memory fallback.

## Redis

**33. What is Redis used for?**
Session caching (faster validation) and rate limiting; it is checked before
MongoDB in the session guard.

**34. What happens if Redis is unavailable?**
The system degrades gracefully — it falls back to MongoDB lookups and
non-cached behaviour.

**35. How does caching speed up verification?**
A cache hit on `session_cache:{token}` returns the session without a database
round-trip.

## Docker

**36. How is the system containerised?**
`docker-compose` defines the FastAPI backend, MongoDB, Redis and nginx services.

**37. Why use nginx?**
As a reverse proxy and static file server in front of the API in containerised
deployments.

**38. How does the dev frontend reach the backend?**
The Vite dev server proxies `/score`, `/auth`, `/session`, `/admin` and
`/api/shadow` to the backend on port 8000.

## Argon2id

**39. What is Argon2id and why use it?**
A memory-hard password-hashing algorithm (winner of the Password Hashing
Competition); memory-hardness resists GPU/ASIC cracking.

**40. How is Argon2id tuned in the system?**
Via presets (memory cost, time cost, parallelism) selected by the Stage-3
governor based on context.

**41. Why memory-hard hashing?**
It raises the cost of offline brute-force by requiring large memory per guess,
limiting parallel attacks.

## Honeypots / Deception

**42. What is Synthetic Success Injection?**
Returning a normal "login succeeded" response to a detected attacker and
transparently routing them into an isolated synthetic environment.

**43. Why deceive instead of block?**
Blocking discloses the defence and forfeits intelligence; deception wastes the
attacker's effort and lets us observe their behaviour.

**44. How is the attacker prevented from detecting the honeypot?**
The success token has the same format as a real token (no detectable prefix);
the "shadow" flag lives only server-side.

**45. What are canary tokens?**
Fake but trackable secrets (e.g. AWS-key-format) placed in the Shadow Admin; any
later use is a high-fidelity exploitation signal.

**46. How is the deception environment kept believable and consistent?**
A deterministic per-session seed drives generation, so the same session sees a
consistent world while different sessions see different data.

**47. What selects the deception strategy?**
The rule-based classifier maps intent to a strategy; a Multi-Armed Bandit (UCB1)
selects the decoy arm in Stage 2.

## Security Framework Design

**48. Is this a replacement for passwords/MFA?**
No — it augments existing authentication with a continuous behavioural layer and
a deception layer.

**49. What are the main security principles applied?**
Continuous verification, detection-without-disclosure, immutable baselines,
defence-in-depth (Argon2id + server-side sessions), and graceful degradation.

**50. What are the known limitations?**
The attack classifier is rule-based (ML is future work); session hijacking maps
to UNKNOWN; durable persistence requires a running MongoDB; and the prototype is
single-tenant. These are documented as roadmap items, not delivered claims.
