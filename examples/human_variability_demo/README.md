# DEMO 4 — Human Variability Handling

The same person types fast, slow, tired, and stressed — and is never falsely
rejected, because the engine scores *relative* drift against an adaptive
baseline, not absolute speed. A different human is still flagged.

```bash
python examples/human_variability_demo/demo.py
```

Demonstrates:  `User A fast  ~=  User A slow   !=   User B`.
