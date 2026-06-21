from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from backend.models.stage1_biometric import (
    analyze_biometrics,
    build_behavioral_baseline,
    calculate_behavioral_risk,
)
from backend.pipeline.stage1_biometric import receive_biometric_event
from backend.services.biometric_services import create_baseline, extract_biometric_features


def _event(user_id: str, day: int = 0, hour: int = 10, device: str = "laptop-1") -> dict:
    ts = datetime(2026, 1, 1, hour, 0, tzinfo=timezone.utc) + timedelta(days=day)
    return {
        "user_id": user_id,
        "timestamp": ts.isoformat(),
        "keystroke_speed": 72,
        "error_rate": 1.5,
        "key_dwell_time": 88,
        "inter_key_delay": 120,
        "mouse_velocity": 420,
        "mouse_acceleration": 35,
        "click_interval": 800,
        "scroll_speed": 250,
        "activity_frequency": 40,
        "session_duration": 1800,
        "device_id": device,
        "ip_address": "10.0.0.5",
        "resource_sensitivity": 0.2,
    }


def test_extract_biometric_features_derives_temporal_and_device_fields():
    features = extract_biometric_features({
        "user_id": "u-features",
        "timestamp": "2026-01-05T03:15:00Z",
        "device_id": "d1",
        "os": "Windows",
        "browser": "Chrome",
        "screen_resolution": "1920x1080",
        "keystroke_intervals": [100, 110, 120],
        "text_length": 60,
        "typing_duration_ms": 60_000,
    })

    assert features["hour_of_day"] == 3
    assert features["is_business_hours"] is False
    assert features["keystroke_speed"] == 60
    assert features["device_fingerprint"]
    assert features["typing_pattern_hash"]


def test_behavioral_baseline_and_anomaly_scoring_flags_new_device_and_time():
    baseline = build_behavioral_baseline(
        [_event("u-risk", day=i, hour=10) for i in range(35)],
        user_id="u-risk",
    )
    current = extract_biometric_features({
        **_event("u-risk", day=40, hour=3, device="unknown-laptop"),
        "keystroke_speed": 130,
        "error_rate": 9.0,
        "ip_address": "203.0.113.44",
        "resource_sensitivity": 0.95,
    })

    analysis = analyze_biometrics(current, baseline)
    risk = calculate_behavioral_risk(analysis)

    assert baseline["baseline_ready"] is True
    assert analysis["is_anomalous"] is True
    assert "unknown_device" in analysis["anomaly_flags"]
    assert "off_hours_access" in analysis["anomaly_flags"]
    assert risk["risk_level"] in {"high", "critical"}
    assert risk["risk_score"] >= 0.65


def test_receive_biometric_event_returns_stage2_ready_payload():
    user_id = "u-pipeline"
    asyncio.run(create_baseline(user_id, [_event(user_id, day=i, hour=10) for i in range(35)]))

    output = asyncio.run(receive_biometric_event({
        **_event(user_id, day=40, hour=2, device="new-device"),
        "ip_address": "198.51.100.9",
        "resource_sensitivity": 0.9,
    }))

    assert output["stage"] == 1
    assert output["baseline_ready"] is True
    assert output["stage2_input"]["biometric_score"] == output["biometric_score"]
    assert output["stage2_input"]["risk_level"] == output["risk_level"]
    assert output["anomaly_flags"]

