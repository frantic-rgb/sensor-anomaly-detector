# H₂ Sensor Anomaly Detector

Real-time anomaly detection for a gaseous hydrogen (H₂) high-pressure endurance test bench.  
Simulates a piston-compressor cycle (0–105 MPa), streams live sensor data via WebSocket, and applies five ML models for comparative anomaly detection.

![Live Dashboard](https://img.shields.io/badge/live-dashboard-0F766E) ![Python](https://img.shields.io/badge/python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features

- **Realistic H₂ test cycle** — piston compressor profile: fast exponential pressure rise, brief hold at 105 MPa, abrupt single-step release, thermal coupling across all sensors
- **Four live sensors** — test pressure (MPa), process gas temperature (°C), H₂ flow (ml/min), specimen surface temperature (°C)
- **Five ML models compared** — Isolation Forest, Local Outlier Factor, One-Class SVM, Elliptic Envelope, Z-Score baseline
- **Live WebSocket stream** — 2 readings/sec, adjustable to 1×/5×/10× speed
- **Model comparison page** — Precision, Recall, F1, FPR table + F1 bar chart + Precision-Recall scatter + detection timeline
- **Labelled dataset export** — CSV with ground-truth labels and predictions from all five models
- **Bundled sample dataset** — 100-cycle reference CSV included in the repo for instant, reproducible model comparison

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   FastAPI Server                │
│                                                 │
│  SensorSimulator  ──►  AnomalyDetector (IF)     │
│       │                      │                  │
│       │              WebSocket /ws              │
│       │                      │                  │
│       └──►  MultiModelDetector                  │
│                 IF · LOF · SVM · EE · Z         │
│                 /api/compare  /api/dataset       │
└────────────────────┬────────────────────────────┘
                     │  HTTP + WS
              ┌──────▼──────┐
              │   Browser   │
              │  index.html │  live dashboard
              │ compare.html│  model comparison
              └─────────────┘
```

**Sensor coupling:**
| Sensor | Behaviour |
|--------|-----------|
| `pressure` | Exponential rise (fast→slow) → hold at 105 MPa → abrupt release |
| `temperature` | Baseline 42 °C + 0.07 °C/MPa compression heating |
| `flow` | ~0.4 ml/min normal fill; 18 ml/min spike on pressure release |
| `specimen_temp` | ~20 °C ambient; drops to ~−25 °C on rapid depressurisation; limit −30 °C |

**Injected anomaly types:**

| Type | Description |
|------|-------------|
| `PRESSURE_DROP` | Valve/seal failure — 15–40 % pressure loss mid-cycle |
| `OVERPRESSURE` | Control failure — 6–12 % above 105 MPa |
| `THERMAL` | Cooling failure — gas temp +28–50 °C |
| `FLOW_SPIKE` | Seal rupture — sustained abnormal H₂ flow |
| `UNDERCOOLING` | Rapid depressurisation — specimen surface −10 to −20 °C below normal |

---

## Quickstart

### Local (Python)

```bash
git clone https://github.com/frantic-rgb/sensor-anomaly-detector.git
cd sensor-anomaly-detector

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker

```bash
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000).

---

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Model metadata and configuration |
| `/api/dataset?cycles=N` | GET | Download labelled CSV (default 100 cycles) |
| `/api/compare?cycles=N` | GET | Run all five models, return JSON metrics + timeline |
| `/ws` | WebSocket | Live sensor stream; send `{"speed": N}` to change rate |

### WebSocket message format

```json
{
  "pressure": 98.4,
  "temperature": 49.1,
  "flow": 0.41,
  "specimen_temp": 22.3,
  "cycle_phase": 0.525,
  "cycle_count": 12,
  "timestamp": 1700000000000,
  "injected_anomaly": false,
  "anomaly_type": null,
  "is_anomaly": false,
  "risk_score": 14,
  "top_sensor": "pressure",
  "speed": 1
}
```

### CSV dataset columns

`cycle_count`, `cycle_phase`, `pressure`, `temperature`, `flow`, `specimen_temp`,  
`injected_anomaly`, `anomaly_type`,  
`isolation_forest_detected`, `isolation_forest_score`,  
`local_outlier_factor_detected`, `local_outlier_factor_score`,  
`one_class_svm_detected`, `one_class_svm_score`,  
`elliptic_envelope_detected`, `elliptic_envelope_score`,  
`zscore_detected`, `zscore_score`

---

## ML Models

All models are trained **unsupervised** on 80 normal cycles (no anomalies).  
Training features: `pressure · temperature · flow · specimen_temp · cycle_phase`

| Model | Approach | Notes |
|-------|----------|-------|
| Isolation Forest | Random tree isolation | Primary live model; conservative threshold |
| Local Outlier Factor | Density-based neighbourhood | Best F1 in benchmark runs |
| One-Class SVM | RBF kernel boundary | Good precision, lower recall |
| Elliptic Envelope | Multivariate Gaussian (Mahalanobis) | High precision, misses subtle faults |
| Z-Score | Max \|z\| across features (σ ≥ 3.2) | Interpretable statistical baseline |

> **Note:** The pressure-release event (phase 0.70–0.83) is a scheduled cycle step,  
> not a fault. The live stream and comparison engine suppress anomaly flags in this  
> window unless a real anomaly (e.g. UNDERCOOLING) is simultaneously injected.

---

## Project Structure

```
sensor-anomaly-detector/
├── app/
│   ├── main.py          # FastAPI routes, WebSocket, startup lifecycle
│   ├── simulator.py     # H₂ test bench physics + anomaly injection
│   ├── detector.py      # Single IsolationForest detector (live stream)
│   └── comparison.py    # Five-model comparison detector
├── static/
│   ├── index.html            # Live dashboard
│   ├── app.js                # WebSocket client, Chart.js charts
│   ├── style.css             # Dark theme
│   ├── compare.html          # Model comparison page
│   ├── compare.js            # Metrics, charts, CSV parser
│   ├── compare.css           # Comparison page styles
│   └── h2_sample_dataset.csv # Bundled 100-cycle reference dataset
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── LICENSE
```

---

## Requirements

```
fastapi==0.111.0
uvicorn[standard]==0.30.1
scikit-learn==1.5.0
numpy==1.26.4
```

Python 3.11 or 3.12 recommended.

---

## License

MIT — see [LICENSE](LICENSE).
