# Entropy Prime — Project Report Structure

## Front Matter
- Title page, Certificate, Declaration, Acknowledgement
- Abstract (see `01_PROJECT_ABSTRACT.md`)
- Table of Contents, List of Figures, List of Tables, Abbreviations

---

## Chapter 1 — Introduction
1.1 Background and context (authentication and web threats)
1.2 Problem statement
1.3 Motivation
1.4 Objectives of the project
1.5 Scope and limitations
1.6 Organisation of the report

## Chapter 2 — Literature Survey
2.1 Authentication models: passwords, MFA, and their limitations
2.2 Behavioural biometrics: keystroke and pointer dynamics
2.3 Continuous / risk-based authentication
2.4 Honeypots and deception technology
2.5 Password hashing (Argon2id) and session security
2.6 Gap analysis — what existing systems do not address
2.7 Summary

## Chapter 3 — System Design
3.1 Requirements (functional and non-functional)
3.2 High-level architecture (User → Behavioral Engine → Identity Verification →
    Attack Classification → Deception Engine → Shadow Environment → Monitoring)
3.3 Four-stage backend pipeline design
3.4 Behavioural feature design and the frozen enrolment template
3.5 Continuous-authentication state machine and confidence zones
3.6 Attack classification rules and intent→strategy mapping
3.7 Deception engine: Synthetic Success Injection and shadow environments
3.8 Data design (collections and contracts)
3.9 Sequence and data-flow diagrams

## Chapter 4 — Implementation
4.1 Technology stack and project structure
4.2 Frontend: capture, identity scoring, AuthContext, TrustContext
4.3 Backend: FastAPI endpoints, orchestrator, session guard
4.4 Deception framework: classifier, injector, shadow world, threat intel
4.5 Persistence: MongoDB/Redis and graceful fallback
4.6 Security: Argon2id, HMAC tokens, server-side sessions
4.7 Deception Demo Lab and attack-pipeline visualisation
4.8 Key algorithms (identity scoring, suspicion accumulator, seeded generation)

## Chapter 5 — Results and Discussion
5.1 Test setup and methodology
5.2 Behavioural discrimination results (owner vs different human)
5.3 Continuous-auth behaviour (zones, idle-freeze, false-positive control)
5.4 Attack classification and routing results (five vectors)
5.5 Shadow environment believability
5.6 End-to-end demonstration validation (build + runtime route audit)
5.7 Component status matrix (see `FINAL_AUDIT.md`)
5.8 Discussion of strengths and limitations

## Chapter 6 — Conclusion and Future Work
6.1 Summary of contributions
6.2 Conclusions
6.3 Future work (ML classifier, contextual-bandit selection, canary
    attribution, multi-tenant hardening)

---

## Back Matter
- References (IEEE format)
- Appendix A — API endpoint reference
- Appendix B — Configuration and deployment
- Appendix C — Demonstration script (see `11_DEMO_SCRIPT.md`)
