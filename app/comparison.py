import numpy as np
from sklearn.covariance import EllipticEnvelope
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

FEATURES      = ["pressure", "temperature", "flow", "specimen_temp", "cycle_phase"]
CONTAMINATION = 0.05
ZSCORE_SIGMA  = 3.2


class MultiModelDetector:
    """
    Trains five anomaly detection models on the same normal-cycle data and
    exposes a single predict_all() call so they can be compared side-by-side.

    All scores are normalised to 0–100 based on the training-data distribution:
      0  = indistinguishable from a normal reading
      100 = most anomalous reading relative to training data

    This makes the scores comparable across models in the timeline chart despite
    the wildly different raw scales (e.g. Mahalanobis distance vs. isolation depth).
    """

    MODEL_NAMES = [
        "isolation_forest",
        "local_outlier_factor",
        "one_class_svm",
        "elliptic_envelope",
        "zscore",
    ]

    MODEL_LABELS = {
        "isolation_forest":     "Isolation Forest",
        "local_outlier_factor": "Local Outlier Factor",
        "one_class_svm":        "One-Class SVM",
        "elliptic_envelope":    "Elliptic Envelope",
        "zscore":               "Z-Score (σ ≥ 3.2)",
    }

    def __init__(self):
        self.scaler = StandardScaler()
        self._sklearn_models = {
            "isolation_forest":     IsolationForest(n_estimators=200, contamination=CONTAMINATION, random_state=42),
            "local_outlier_factor": LocalOutlierFactor(n_neighbors=20, contamination=CONTAMINATION, novelty=True),
            "one_class_svm":        OneClassSVM(kernel="rbf", nu=CONTAMINATION, gamma="scale"),
            "elliptic_envelope":    EllipticEnvelope(contamination=CONTAMINATION, random_state=42),
        }
        # Percentile bounds fitted during training — used to normalise scores to 0-100
        self._score_lo: dict[str, float] = {}
        self._score_hi: dict[str, float] = {}
        self.trained = False

    def train(self, X: np.ndarray | None = None) -> None:
        from app.simulator import SensorSimulator
        if X is None:
            X = SensorSimulator(anomaly_rate=0.0).generate_normal_data(80)
        Xs = self.scaler.fit_transform(X)
        for name, model in self._sklearn_models.items():
            model.fit(Xs)
            # Raw scores on training data: negate so higher = more anomalous for all models
            raw_scores = -model.score_samples(Xs)
            self._score_lo[name] = float(np.percentile(raw_scores, 1))
            self._score_hi[name] = float(np.percentile(raw_scores, 99))
        self.trained = True

    def _normalise(self, name: str, raw: float) -> float:
        """Map raw score to 0–100 using training-data percentile bounds."""
        lo, hi = self._score_lo[name], self._score_hi[name]
        if hi <= lo:
            return 0.0
        return round(min(100.0, max(0.0, (raw - lo) / (hi - lo) * 100)), 1)

    def predict_all(self, reading: dict) -> dict:
        x  = np.array([[reading[f] for f in FEATURES]])
        xs = self.scaler.transform(x)

        results = {}
        for name, model in self._sklearn_models.items():
            label = int(model.predict(xs)[0])           # 1 = normal, −1 = anomaly
            raw   = float(-model.score_samples(xs)[0])  # higher = more anomalous
            results[name] = {
                "detected": label == -1,
                "score":    self._normalise(name, raw),
            }

        max_z = float(np.max(np.abs(xs[0])))
        norm_z = round(min(100.0, max(0.0, max_z / ZSCORE_SIGMA * 50)), 1)
        results["zscore"] = {
            "detected": max_z >= ZSCORE_SIGMA,
            "score":    norm_z,
        }

        return results
