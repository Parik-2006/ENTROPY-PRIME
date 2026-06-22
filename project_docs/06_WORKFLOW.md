# Entropy Prime — End-to-End Workflows

## 1. Normal User Flow

```mermaid
flowchart TD
    A[User opens app] --> B[Login: email + password]
    B --> C[Argon2id verify + create session]
    C --> D[Enrollment: type 5 prompts]
    D --> E[Frozen template captured]
    E --> F[Dashboard]
    F --> G{Heartbeat + live identity}
    G -->|confidence >= 80| H[Trusted — uninterrupted]
    G -->|idle| H
    H --> F
```

## 2. Impostor Detection Flow

```mermaid
flowchart TD
    A[Different person types on an open session] --> B[computeIdentity vs frozen template]
    B --> C{Typing + digraph similarity}
    C -->|low, not corroborated| D[score decays gradually 95→...→58]
    D --> E[suspicion accumulates over rolling window]
    E --> F{sustained < 60 ?}
    F -->|no| G[Monitor zone — banner only]
    F -->|yes| H[Re-auth modal]
    H --> I[Verify Identity]
    I --> J[trust reset + cooldown started]
    G --> B
```

## 3. Credential Stuffing Flow

```mermaid
flowchart TD
    A[Bot: many usernames] --> B[/POST /score: distinct_usernames high/]
    B --> C[Stage1: BOT verdict]
    C --> D[Classifier: CREDENTIAL_STUFFING]
    D --> E[Synthetic Success: status success]
    E --> F[Banking Shadow World]
    F --> G[Accounts / Transactions / Beneficiaries]
    G --> H[Monitoring: shadow_start + api_call]
```

## 4. Reconnaissance Flow

```mermaid
flowchart TD
    A[Recon: admin path probing] --> B[/POST /score: admin_path_hits, 404 ratio/]
    B --> C[Classifier: RECON]
    C --> D[Synthetic Success → redirect /admin]
    D --> E[Shadow Admin World]
    E --> F[Users / Logs / Analytics / Config]
    F --> G[Secrets page: CANARY API keys]
    G --> H[Monitoring: canary_hit recorded]
```

## 5. Data Scraper Flow

```mermaid
flowchart TD
    A[Scraper: high request rate] --> B[/POST /score: request_rate high/]
    B --> C[Classifier: SCRAPER]
    C --> D[Synthetic Dataset]
    D --> E[Large paginated transactions feed]
    E --> F[Deep, deterministic pagination]
    F --> G[Monitoring: api_call per page]
```

## 6. Brute Force Flow

```mermaid
flowchart TD
    A[Brute force: many passwords] --> B[/POST /score: password_attempts high/]
    B --> C[Classifier: BRUTE_FORCE]
    C --> D[Tarpit Environment]
    D --> E[Believable, deliberately slowed success flow]
    E --> F[Monitoring: dwell time recorded]
```

## 7. Session Hijacking Flow

```mermaid
flowchart TD
    A[Session abuse: ambiguous signals] --> B[/POST /score/]
    B --> C[Classifier: UNKNOWN]
    C --> D[Restricted Session Sandbox]
    D --> E[Limited subset: overview + profile only]
    E --> F[Notice: re-verify to view full details]
    F --> G[Monitoring: limited interaction logged]
```

> In the delivered prototype the classifier has five classes; Session Hijacking
> maps to UNKNOWN and is presented as a restricted sandbox at the UI layer. A
> dedicated "session abuse" class is a documented roadmap item.
