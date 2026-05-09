# CLAUDE IMPLEMENTATION PROMPT

## Ganesh

Claude, please help Ganesh implement the first-user typing flow in simple words. The app should learn a normal typing pattern first, save that baseline, and then detect when the same user starts typing very fast or with random alphabets. If the behavior looks wrong, the system should warn the user and ask for re-authentication. If the tests fail, do not make only a small fix. Improve the flow, make the typing sample path clear, and make the behavior easy to test and explain.

Files and locations for Ganesh:

- Frontend: [src/pages/LoginPage.jsx](src/pages/LoginPage.jsx) - start typing capture during login.
- Frontend: [src/services/biometrics.js](src/services/biometrics.js) - typing sample collection and pattern comparison.
- Frontend: [src/context/AuthContext.jsx](src/context/AuthContext.jsx) - session state and re-auth handling.
- Frontend: [src/pages/ThreatPage.jsx](src/pages/ThreatPage.jsx) - show warning and suspicious activity.
- Backend: [backend/pipeline/stage1_biometric.py](backend/pipeline/stage1_biometric.py) - score the typing pattern.
- Backend: [backend/main.py](backend/main.py) - route flow for login and re-auth decisions.
- Backend: [backend/tests/test_stage1_biometric.py](backend/tests/test_stage1_biometric.py) - typing pattern tests.
- Support: [TEAM_TEST_PLAN.md](TEAM_TEST_PLAN.md) - keep the human test steps aligned.

## Ved

Claude, please help Ved implement the continuous monitoring flow in simple words. While the user stays logged in, the app should keep checking the live typing pattern against the stored user pattern. If another person starts typing, the pattern should change, and the system should trigger re-authentication. If the tests fail, improve the monitoring design, make the decision path clearer, and keep the logic simple enough for repeated testing.

Files and locations for Ved:

- Frontend: [src/pages/DashboardPage.jsx](src/pages/DashboardPage.jsx) - show live session and monitoring state.
- Frontend: [src/pages/ThreatPage.jsx](src/pages/ThreatPage.jsx) - display mismatch or re-auth warnings.
- Frontend: [src/services/biometrics.js](src/services/biometrics.js) - compare live input with the saved pattern.
- Frontend: [src/context/AuthContext.jsx](src/context/AuthContext.jsx) - keep the logged-in session state.
- Backend: [backend/pipeline/stage4_watchdog.py](backend/pipeline/stage4_watchdog.py) - continuous trust and monitoring logic.
- Backend: [backend/pipeline/orchestrator.py](backend/pipeline/orchestrator.py) - connect the live checks to the pipeline.
- Backend: [backend/main.py](backend/main.py) - session verification and re-auth trigger flow.
- Backend: [backend/tests/test_stage4_watchdog.py](backend/tests/test_stage4_watchdog.py) - live monitoring tests.
- Backend: [backend/tests/test_integration.py](backend/tests/test_integration.py) - end-to-end session flow.

## Vivek

Claude, please help Vivek implement and test the honeypot flow in simple words. Run a normal app session in one terminal or tab and run a bot script in another terminal or tab. The app should detect bot-like behavior, trigger the honeypot, and return safe or fake data instead of real sensitive data. If the tests fail, improve the architecture, make the bot-test path clearer, and keep the honeypot behavior easy to verify.

Files and locations for Vivek:

- Backend: [backend/pipeline/stage2_honeypot.py](backend/pipeline/stage2_honeypot.py) - bot detection and honeypot response.
- Backend: [backend/main.py](backend/main.py) - route handling for honeypot triggers.
- Backend: [backend/pipeline/orchestrator.py](backend/pipeline/orchestrator.py) - connect honeypot decisions to the pipeline.
- Backend: [backend/tests/test_stage2_honeypot.py](backend/tests/test_stage2_honeypot.py) - honeypot and bot behavior tests.
- Backend: [backend/tests/test_integration.py](backend/tests/test_integration.py) - full flow check with the running app.
- Support: [start.bat](start.bat) and [start.sh](start.sh) - use these to run the app while testing the bot.
- Support: [README.md](README.md) - update run and test instructions if the flow changes.

## Shared goal

All three prompts should follow the same idea: keep the implementation simple, make the file locations clear, update both frontend and backend when needed, and make the test flow easy to repeat until the whole system is stable.