import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


class AnomalyDetector:
    FEATURES     = ["pressure", "temperature", "flow", "specimen_temp", "cycle_phase"]
    REAL_SENSORS = ["pressure", "temperature", "flow", "specimen_temp"]

    def __init__(self):
        self.forest = IsolationForest(
            n_estimators=200,
            contamination=0.05,
            random_state=42,
        )
        self.scaler  = StandardScaler()
        self.trained = False
        self._score_lo = 0.05
        self._score_hi = 0.40

    def train(self, X: np.ndarray | None = None) -> None:
        from app.simulator import SensorSimulator
        if X is None:
            X = SensorSimulator(anomaly_rate=0.0).generate_normal_data(80)
        X_scaled = self.scaler.fit_transform(X)
        self.forest.fit(X_scaled)
        scores = -self.forest.score_samples(X_scaled)
        self._score_lo = float(np.percentile(scores, 2))
        self._score_hi = float(np.percentile(scores, 99))
        self.trained = True

    def predict(self, reading: dict) -> dict:
        x = np.array([[reading[f] for f in self.FEATURES]])
        x_scaled = self.scaler.transform(x)

        label = int(self.forest.predict(x_scaled)[0])
        raw   = float(-self.forest.score_samples(x_scaled)[0])
        risk  = int(max(0, min(100, (raw - self._score_lo) / (self._score_hi - self._score_lo) * 100)))

        vals  = np.array([reading[s] for s in self.REAL_SENSORS])
        means = self.scaler.mean_[:4]
        stds  = np.sqrt(self.scaler.var_[:4])
        z     = np.abs((vals - means) / stds)
        top   = self.REAL_SENSORS[int(np.argmax(z))]

        return {
            "is_anomaly": label == -1,
            "risk_score": risk,
            "top_sensor": top,
        }
