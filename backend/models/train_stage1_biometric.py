"""Training helpers for PARIK Stage 1 behavioral biometric models."""
from __future__ import annotations

import json
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .stage1_biometric import BEHAVIORAL_NUMERIC_FEATURES
from ..services.biometric_services import extract_biometric_features


def prepare_training_matrix(samples: Iterable[dict[str, Any]]) -> tuple[list[list[float]], list[str]]:
    """Convert raw or extracted events into a numeric feature matrix."""
    rows = [
        sample if "keystroke_speed" in sample else extract_biometric_features(sample)
        for sample in samples
    ]
    feature_names = [
        name for name in BEHAVIORAL_NUMERIC_FEATURES
        if any(row.get(name) is not None for row in rows)
    ]
    matrix = [
        [_as_float(row.get(name)) for name in feature_names]
        for row in rows
    ]
    return matrix, feature_names


def train_isolation_forest(
    samples: Iterable[dict[str, Any]],
    *,
    output_path: str | Path | None = None,
    contamination: str | float = "auto",
) -> dict[str, Any]:
    """
    Train the unsupervised Isolation Forest requested by the Stage 1 spec.

    Returns metadata even when sklearn is unavailable, so CI can still import
    this module before the optional ML dependency is installed.
    """
    started = time.perf_counter()
    matrix, feature_names = prepare_training_matrix(samples)
    if len(matrix) < 8 or len(feature_names) < 2:
        return _metadata(
            feature_names,
            status="insufficient_data",
            inference_latency_ms=0.0,
            sample_count=len(matrix),
        )

    try:
        from sklearn.ensemble import IsolationForest  # type: ignore
    except Exception:
        return _metadata(
            feature_names,
            status="sklearn_unavailable",
            inference_latency_ms=0.0,
            sample_count=len(matrix),
        )

    model = IsolationForest(contamination=contamination, random_state=7)
    model.fit(matrix)
    latency_ms = (time.perf_counter() - started) * 1000
    metadata = _metadata(
        feature_names,
        status="ready",
        inference_latency_ms=latency_ms,
        sample_count=len(matrix),
    )

    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump({"model": model, "metadata": metadata}, fh)
        path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        metadata["model_path"] = str(path)

    return metadata


def train_stage1_models(samples: Iterable[dict[str, Any]], output_dir: str | Path = "checkpoints") -> dict[str, Any]:
    """Train all currently implemented Stage 1 models and return deployment metadata."""
    output_dir = Path(output_dir)
    model_path = output_dir / "biometric_isolation_forest.pkl"
    isolation = train_isolation_forest(samples, output_path=model_path)
    return {
        "model_type": "stage1_behavioral_ensemble",
        "training_date": datetime.now(timezone.utc).isoformat(),
        "models_trained": ["isolation_forest"] if isolation["deployment_status"] == "ready" else [],
        "baseline_updated": False,
        "performance_metrics": {
            "accuracy": None,
            "precision": None,
            "recall": None,
            "f1_score": None,
        },
        "concept_drift_detected": False,
        "feedback_incorporated": 0,
        "deployment_status": isolation["deployment_status"],
        "isolation_forest": isolation,
    }


def _metadata(
    feature_names: list[str],
    *,
    status: str,
    inference_latency_ms: float,
    sample_count: int,
) -> dict[str, Any]:
    return {
        "model_type": "isolation_forest",
        "training_date": datetime.now(timezone.utc).isoformat(),
        "feature_names": feature_names,
        "sample_count": sample_count,
        "inference_latency_ms": round(inference_latency_ms, 3),
        "false_positive_rate": None,
        "false_negative_rate": None,
        "deployment_status": status,
    }


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0

