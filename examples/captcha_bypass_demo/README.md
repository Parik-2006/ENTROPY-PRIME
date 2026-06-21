# DEMO 1 — CAPTCHA Bypass

Shows why a one-time CAPTCHA is insufficient: a bot that *passes* the CAPTCHA
(via Selenium/Puppeteer/Buster or a human-solver farm) is still caught by
continuous behavioral scoring.

```bash
python examples/captcha_bypass_demo/demo.py
```

Traditional CAPTCHA-only gate → ALLOW. Entropy Prime behavioral gate →
shadow-routed. A real human is served normally.
