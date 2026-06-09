import asyncio
import csv
import io
import pathlib
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.comparison import MultiModelDetector
from app.detector import AnomalyDetector
from app.simulator import SensorSimulator

# ── Constants ─────────────────────────────────────────────────────────────

SAMPLE_PATH   = pathlib.Path(__file__).parent.parent / "static" / "h2_sample_dataset.csv"
SAMPLE_CYCLES = 100
ANOMALY_RATE  = 0.06
BASE_INTERVAL = 0.5   # seconds per WebSocket reading at 1× speed


# ── Application state ─────────────────────────────────────────────────────

@dataclass
class AppState:
    stream_interval: float = BASE_INTERVAL


_state    = AppState()
simulator = SensorSimulator(anomaly_rate=ANOMALY_RATE)
detector  = AnomalyDetector()
detector.train()


# ── Startup: pre-generate sample dataset ─────────────────────────────────

def _generate_sample_file() -> None:
    """Pre-generate a labelled 100-cycle dataset with predictions from all five models."""
    sim = SensorSimulator(anomaly_rate=ANOMALY_RATE)
    mmd = MultiModelDetector()
    mmd.train()

    base_fields  = ["cycle_count", "cycle_phase",
                    "pressure", "temperature", "flow", "specimen_temp",
                    "injected_anomaly", "anomaly_type"]
    model_fields = [f"{m}_{s}" for m in mmd.MODEL_NAMES for s in ("detected", "score")]

    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SAMPLE_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=base_fields + model_fields)
        writer.writeheader()
        for _ in range(SAMPLE_CYCLES * SensorSimulator.CYCLE_STEPS):
            reading = sim.next()
            preds   = mmd.predict_all(reading)
            row = {
                "cycle_count":      reading["cycle_count"],
                "cycle_phase":      reading["cycle_phase"],
                "pressure":         reading["pressure"],
                "temperature":      reading["temperature"],
                "flow":             reading["flow"],
                "specimen_temp":    reading["specimen_temp"],
                "injected_anomaly": reading["injected_anomaly"],
                "anomaly_type":     reading["anomaly_type"] or "",
            }
            for m in mmd.MODEL_NAMES:
                row[f"{m}_detected"] = preds[m]["detected"]
                row[f"{m}_score"]    = preds[m]["score"]
            writer.writerow(row)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not SAMPLE_PATH.exists():
        # Run in background so the server starts accepting requests immediately
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _generate_sample_file)
    yield


# ── App ───────────────────────────────────────────────────────────────────

app = FastAPI(title="H₂ Sensor Anomaly Detector", lifespan=lifespan)


# ── REST endpoints ────────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    return {
        "status":            "running",
        "model":             "IsolationForest",
        "library":           "scikit-learn",
        "training_cycles":   80,
        "contamination":     0.05,
        "sensors":           AnomalyDetector.REAL_SENSORS,
        "features":          AnomalyDetector.FEATURES,
        "stream_interval_ms": round(_state.stream_interval * 1000),
        "medium":            "H₂ gaseous",
        "p_max_mpa":         105,
    }


@app.get("/api/dataset")
def export_dataset(cycles: int = 100):
    """Labelled CSV with ground-truth labels and predictions from all five models."""
    mmd  = MultiModelDetector()
    mmd.train()
    sim  = SensorSimulator(anomaly_rate=ANOMALY_RATE)

    base_fields  = ["cycle_count", "cycle_phase",
                    "pressure", "temperature", "flow", "specimen_temp",
                    "injected_anomaly", "anomaly_type"]
    model_fields = [f"{m}_{s}" for m in mmd.MODEL_NAMES for s in ("detected", "score")]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=base_fields + model_fields)
    writer.writeheader()

    for _ in range(cycles * SensorSimulator.CYCLE_STEPS):
        reading = sim.next()
        preds   = mmd.predict_all(reading)
        row = {
            "cycle_count":      reading["cycle_count"],
            "cycle_phase":      reading["cycle_phase"],
            "pressure":         reading["pressure"],
            "temperature":      reading["temperature"],
            "flow":             reading["flow"],
            "specimen_temp":    reading["specimen_temp"],
            "injected_anomaly": reading["injected_anomaly"],
            "anomaly_type":     reading["anomaly_type"] or "",
        }
        for m in mmd.MODEL_NAMES:
            row[f"{m}_detected"] = preds[m]["detected"]
            row[f"{m}_score"]    = preds[m]["score"]
        writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=h2_dataset_{cycles}cycles.csv"},
    )


@app.get("/api/compare")
def compare_models(cycles: int = 100):
    """Run all five models on the same simulated dataset; return metrics + timeline."""
    mmd = MultiModelDetector()
    mmd.train()
    sim = SensorSimulator(anomaly_rate=ANOMALY_RATE)

    counters       = {m: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for m in mmd.MODEL_NAMES}
    timeline: list = []
    step           = 0
    total_injected = 0

    for _ in range(cycles * SensorSimulator.CYCLE_STEPS):
        reading = sim.next()
        preds   = mmd.predict_all(reading)
        truth   = reading["injected_anomaly"]
        phase   = reading["cycle_phase"]

        if truth:
            total_injected += 1

        # Suppress false positives during the scheduled release window
        in_release = (SensorSimulator.HOLD_END <= phase
                      <= SensorSimulator.HOLD_END + SensorSimulator.F_DECAY_WIDTH)

        for m in mmd.MODEL_NAMES:
            detected = preds[m]["detected"] and not (in_release and not truth)
            if truth and detected:       counters[m]["tp"] += 1
            elif not truth and detected: counters[m]["fp"] += 1
            elif truth and not detected: counters[m]["fn"] += 1
            else:                        counters[m]["tn"] += 1

        if step % 4 == 0:
            timeline.append({
                "step":  step,
                "cycle": reading["cycle_count"],
                "phase": phase,
                "truth": truth,
                **{f"{m}_score": preds[m]["score"] for m in mmd.MODEL_NAMES},
                **{f"{m}_det":   preds[m]["detected"] for m in mmd.MODEL_NAMES},
            })
        step += 1

    metrics = {}
    for m in mmd.MODEL_NAMES:
        c   = counters[m]
        pr  = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) > 0 else 0.0
        rc  = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) > 0 else 0.0
        f1  = 2 * pr * rc / (pr + rc)       if (pr + rc)           > 0 else 0.0
        fpr = c["fp"] / (c["fp"] + c["tn"]) if (c["fp"] + c["tn"]) > 0 else 0.0
        metrics[m] = {
            "label":     mmd.MODEL_LABELS[m],
            "tp": c["tp"], "fp": c["fp"], "fn": c["fn"], "tn": c["tn"],
            "precision": round(pr,  3),
            "recall":    round(rc,  3),
            "f1":        round(f1,  3),
            "fpr":       round(fpr, 3),
        }

    return {
        "cycles":         cycles,
        "total_steps":    step,
        "total_injected": total_injected,
        "metrics":        metrics,
        "model_names":    mmd.MODEL_NAMES,
        "model_labels":   mmd.MODEL_LABELS,
        "timeline":       timeline,
    }


# ── WebSocket live stream ─────────────────────────────────────────────────

@app.websocket("/ws")
async def stream(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=0.001)
                if isinstance(msg, dict) and "speed" in msg:
                    factor = float(msg["speed"])
                    _state.stream_interval = round(max(0.05, BASE_INTERVAL / factor), 3)
            except (asyncio.TimeoutError, Exception):
                pass

            reading = simulator.next()
            result  = detector.predict(reading)
            phase   = reading["cycle_phase"]

            if SensorSimulator.HOLD_END <= phase <= SensorSimulator.HOLD_END + SensorSimulator.F_DECAY_WIDTH:
                result["is_anomaly"] = reading["injected_anomaly"]
                if not reading["injected_anomaly"]:
                    result["risk_score"] = 0

            await ws.send_json({
                **reading,
                **result,
                "speed": round(BASE_INTERVAL / _state.stream_interval),
            })
            await asyncio.sleep(_state.stream_interval)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# Static files — must be mounted last so explicit routes above take priority
app.mount("/", StaticFiles(directory="static", html=True), name="static")
