# Entropy Prime — System Architecture

## 1. High-level pipeline

The system is organised as a layered pipeline. A user's interaction is observed
by the behavioural engine, identity is continuously verified, malicious traffic
is classified and routed by the deception engine into a shadow environment, and
all activity feeds the monitoring layer.

```mermaid
flowchart TD
    U[User / Client] --> BE[Behavioral Engine<br/>keystroke + pointer capture]
    BE --> IV[Identity Verification<br/>frozen-template scoring]
    IV -->|trusted| APP[Real Application<br/>Entropy Bank]
    IV -->|sustained mismatch| RE[Re-Authentication]
    U -. malicious request .-> AC[Attack Classification]
    AC --> DE[Deception Engine<br/>Synthetic Success Injection]
    DE --> SE[Shadow Environment<br/>banking / admin / dataset / tarpit / sandbox]
    SE --> MON[Monitoring Layer<br/>threat-intelligence store]
    RE --> APP
```

## 2. Component architecture

```mermaid
flowchart LR
    subgraph Client[Frontend · React + Vite + TF.js]
        LP[LoginPage / EnrollPage]
        SH[AppShell + Bank pages]
        BIO[biometrics.js<br/>capture + CNN + autoencoder + identity scorer]
        AUTH[AuthContext<br/>session + heartbeat]
        TRUST[TrustContext<br/>confidence zones]
        LAB[Deception Demo Lab<br/>AttackPipeline + ShadowEnvView]
    end

    subgraph Server[Backend · FastAPI + Python]
        SCORE[/POST /score/]
        VERIFY[/POST /session/verify/]
        AUTHR[/POST /auth/login, /biometric/profile/]
        ORCH[PipelineOrchestrator<br/>Stage1..4]
        CLS[deception.classifier]
        INJ[synthetic_success injector]
        SAPI[/GET /api/shadow/*/]
    end

    subgraph Data[Persistence]
        MDB[(MongoDB)]
        RDS[(Redis)]
    end

    LP --> AUTHR
    BIO --> AUTH
    AUTH --> VERIFY
    LAB --> SCORE
    SCORE --> ORCH --> CLS --> INJ
    LAB --> SAPI
    AUTHR --> MDB
    VERIFY --> MDB
    VERIFY --> RDS
    INJ --> MDB
```

## 3. Four-stage backend pipeline

The `PipelineOrchestrator` executes four stages per `/score` call:

```mermaid
flowchart TD
    IN[BiometricInput<br/>theta, h_exp, server_load, signals] --> S1[Stage 1 · Biometric<br/>humanity verdict + confidence]
    S1 --> S2[Stage 2 · Honeypot<br/>_should_shadow? + MAB arm]
    S2 -->|shadow| SHADOW[Synthetic Success<br/>+ classifier + shadow session]
    S2 -->|human| S3[Stage 3 · Governor<br/>Argon2id preset / DQN+PPO]
    S3 --> S4[Stage 4 · Watchdog<br/>continuous drift]
    SHADOW --> OUT[PipelineOutput]
    S4 --> OUT
```

- **Stage 1 — Biometric:** maps the humanity signal `theta` to a verdict
  (BOT / SUSPECT / HUMAN) with a confidence band.
- **Stage 2 — Honeypot:** decides shadow routing (`_should_shadow`) and selects
  a deception arm via a Multi-Armed Bandit; on shadow, hands off to the
  deception control plane.
- **Stage 3 — Governor:** selects an Argon2id hardening preset (skipped for
  shadow traffic, which uses an economy preset).
- **Stage 4 — Watchdog:** the continuous-drift signal used by the heartbeat.

## 4. Continuous-authentication data flow

```mermaid
sequenceDiagram
    participant U as User
    participant ENG as biometrics.js
    participant AC as AuthContext
    participant TC as TrustContext
    participant BE as Backend /session/verify

    U->>ENG: types / moves (captured)
    loop every 1.5 s (live eval)
        ENG->>ENG: computeIdentity() vs frozen template
        ENG->>AC: identity score → trustScore
    end
    AC->>TC: trustScore
    TC->>TC: confidence → zone (Trusted/Monitor/Reauth)
    loop every 30 s (heartbeat)
        AC->>BE: POST /session/verify (X-Session-Token)
        BE-->>AC: 200 (ok) or 401 (clean logout)
    end
    TC-->>U: re-auth modal only if confidence < 60 sustained
```

## 5. Deception control plane

```mermaid
flowchart TD
    SCORE[/score: shadow_mode=true/] --> CLS[classify AttackSignals]
    CLS --> INJ[mint synthetic success token]
    INJ --> STORE[(ShadowStateStore<br/>server-side flag)]
    STORE --> WORLD[ShadowWorldEngine]
    WORLD --> BANK[BankingProfile]
    WORLD --> ADMIN[ShadowAdminProfile]
    INJ --> REC[ThreatIntelRecorder]
    REC --> MDB[(MongoDB best-effort)]
```

## 6. Key architectural principles

- **Detection ≠ disclosure:** classified attackers receive a normal success
  response; the "this is shadow" fact lives only server-side.
- **Frozen baseline:** the enrolment template is immutable; verification never
  adapts it, so an impostor cannot become the new baseline.
- **Graceful degradation:** when MongoDB is unreachable the backend falls back
  to an in-memory mock; in-process stores keep the demo functional.
- **Additive design:** the deception layer composes the existing pipeline
  without modifying it.
