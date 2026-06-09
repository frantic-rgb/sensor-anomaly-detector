"""Score range tests: all models must return scores in [0, 100] for any input."""
import pytest
from app.simulator import SensorSimulator
from app.detector import AnomalyDetector
from app.comparison import MultiModelDetector


@pytest.fixture(scope="module")
def detector():
    det = AnomalyDetector()
    det.train()
    return det


@pytest.fixture(scope="module")
def multi_detector():
    mmd = MultiModelDetector()
    mmd.train()
    return mmd


@pytest.fixture(scope="module")
def normal_readings():
    sim = SensorSimulator(anomaly_rate=0.0)
    return [sim.next() for _ in range(SensorSimulator.CYCLE_STEPS * 3)]


@pytest.fixture(scope="module")
def anomaly_readings():
    sim = SensorSimulator(anomaly_rate=1.0)
    return [sim.next() for _ in range(SensorSimulator.CYCLE_STEPS * 3)]


class TestIsolationForestScores:
    def test_score_range_normal(self, detector, normal_readings):
        for r in normal_readings:
            result = detector.predict(r)
            assert 0 <= result["risk_score"] <= 100, (
                f"risk_score {result['risk_score']} out of range at phase {r['cycle_phase']:.3f}"
            )

    def test_score_range_anomalies(self, detector, anomaly_readings):
        for r in anomaly_readings:
            result = detector.predict(r)
            assert 0 <= result["risk_score"] <= 100, (
                f"risk_score {result['risk_score']} out of range (type={r['anomaly_type']})"
            )

    def test_result_has_required_keys(self, detector, normal_readings):
        result = detector.predict(normal_readings[0])
        assert "is_anomaly" in result
        assert "risk_score" in result
        assert "top_sensor" in result
        assert isinstance(result["is_anomaly"], bool)


class TestMultiModelScores:
    @pytest.mark.parametrize("model", MultiModelDetector.MODEL_NAMES)
    def test_score_range_normal(self, multi_detector, normal_readings, model):
        for r in normal_readings:
            score = multi_detector.predict_all(r)[model]["score"]
            assert 0 <= score <= 100, (
                f"{model} score {score} out of range at phase {r['cycle_phase']:.3f}"
            )

    @pytest.mark.parametrize("model", MultiModelDetector.MODEL_NAMES)
    def test_score_range_anomalies(self, multi_detector, anomaly_readings, model):
        for r in anomaly_readings:
            score = multi_detector.predict_all(r)[model]["score"]
            assert 0 <= score <= 100, (
                f"{model} score {score} out of range (type={r['anomaly_type']})"
            )

    @pytest.mark.parametrize("model", MultiModelDetector.MODEL_NAMES)
    def test_detected_is_bool(self, multi_detector, normal_readings, model):
        result = multi_detector.predict_all(normal_readings[0])[model]
        assert isinstance(result["detected"], bool)
