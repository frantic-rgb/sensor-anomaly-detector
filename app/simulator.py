import math
import time
from enum import Enum, auto

import numpy as np


class AnomalyType(Enum):
    PRESSURE_DROP  = auto()   # valve/seal failure → pressure loss during cycle
    OVERPRESSURE   = auto()   # control failure → exceeds 105 MPa limit
    THERMAL        = auto()   # cooling failure → gas temperature excursion
    FLOW_SPIKE     = auto()   # seal rupture → sustained abnormal H₂ flow
    UNDERCOOLING   = auto()   # rapid depressurisation → specimen below −30 °C


class SensorSimulator:
    """
    Simulates an H₂ high-pressure endurance test bench (gaseous hydrogen, 0–105 MPa).

    Sensors:
      pressure      — test pressure (MPa), piston-compressor profile
      temperature   — process gas temperature (°C)
      flow          — H₂ volumetric flow into the system (ml/min)
      specimen_temp — component surface temperature (°C); drops on fast depressurisation

    Cycle geometry (piston compressor):
      rise    0 → RISE_END   : exponential approach — fast at first, slowing toward target
      hold    RISE_END → HOLD_END : at P_MAX
      release HOLD_END → RELEASE_END : abrupt 1-step drop
      recovery RELEASE_END → 1.0 : depressurised, flow/temp recover
    """

    CYCLE_STEPS   = 40       # readings per full cycle (20 s at 2 Hz)
    P_MAX         = 105.0    # MPa — peak H₂ test pressure
    P_NOISE_FLOOR = 0.4      # MPa absolute noise
    P_NOISE_REL   = 0.003    # 0.3 % relative noise

    RISE_END    = 0.65   # pressurisation complete
    HOLD_END    = 0.70   # hold ends → release starts
    RELEASE_END = 0.725  # pressure at zero (~1 step: abrupt)

    # Process gas temperature — couples with pressure (compression heating)
    T_MEAN, T_STD = 42.0, 1.0   # °C baseline
    T_P_COEFF     = 0.07         # °C/MPa

    # H₂ flow into system
    F_MEAN, F_STD = 0.40, 0.10  # ml/min normal fill flow
    F_PEAK        = 18.0         # ml/min peak on pressure release
    F_DECAY_WIDTH = 0.125        # phase width of post-release flow decay

    # Specimen (component) surface temperature
    T_SPEC_AMBIENT  = 20.0   # °C ambient
    T_SPEC_P_COEFF  = 0.02   # slight warming from compressed gas conduction (°C/MPa)
    T_SPEC_DROP     = -47.0  # °C instantaneous drop on depressurisation
    T_SPEC_RECOVERY = 0.30   # phase width for thermal recovery
    T_SPEC_STD      = 1.5    # °C sensor noise
    T_SPEC_LIMIT    = -30.0  # °C minimum allowed specimen temperature

    def __init__(self, anomaly_rate: float = 0.05):
        self.anomaly_rate = anomaly_rate
        self.rng = np.random.default_rng()
        self._step = 0
        self._cycle_count = 0
        self._in_anomaly = False
        self._anomaly_ticks = 0
        self._anomaly_type: AnomalyType | None = None
        self._cooldown = 0

    # ── Cycle geometry ────────────────────────────────────────────────────

    @property
    def _phase(self) -> float:
        return (self._step % self.CYCLE_STEPS) / self.CYCLE_STEPS

    def _p_expected(self, phase: float) -> float:
        if phase < self.RISE_END:
            t = phase / self.RISE_END
            return self.P_MAX * (1.0 - math.exp(-4.5 * t)) / (1.0 - math.exp(-4.5))
        elif phase < self.HOLD_END:
            return self.P_MAX
        elif phase < self.RELEASE_END:
            t = (phase - self.HOLD_END) / (self.RELEASE_END - self.HOLD_END)
            return self.P_MAX * (1.0 - t)
        else:
            return 0.0

    def _flow_expected(self, phase: float) -> float:
        """Normal H₂ fill flow plus post-release discharge spike."""
        if self.HOLD_END <= phase < self.HOLD_END + self.F_DECAY_WIDTH:
            t = (phase - self.HOLD_END) / self.F_DECAY_WIDTH
            return self.F_MEAN + self.F_PEAK * math.exp(-5.0 * t)
        return self.F_MEAN

    def _specimen_temp_expected(self, phase: float) -> float:
        """Component surface temp: slight compression warming, sharp drop on release."""
        p = self._p_expected(phase)
        t_base = self.T_SPEC_AMBIENT + self.T_SPEC_P_COEFF * p
        if self.HOLD_END <= phase < self.HOLD_END + self.T_SPEC_RECOVERY:
            t = (phase - self.HOLD_END) / self.T_SPEC_RECOVERY
            drop = self.T_SPEC_DROP * math.exp(-4.0 * t)
            return t_base + drop
        return t_base

    # ── Anomaly state machine ─────────────────────────────────────────────

    def _tick_anomaly(self) -> tuple[bool, AnomalyType | None]:
        if self._in_anomaly:
            self._anomaly_ticks -= 1
            if self._anomaly_ticks <= 0:
                self._in_anomaly = False
                self._anomaly_type = None
                self._cooldown = int(self.rng.integers(15, 30))
            return self._in_anomaly or self._anomaly_ticks == 0, self._anomaly_type

        if self._cooldown > 0:
            self._cooldown -= 1
            return False, None

        if self.rng.random() < self.anomaly_rate:
            self._in_anomaly = True
            self._anomaly_ticks = int(self.rng.integers(5, 12))
            self._anomaly_type = AnomalyType(self.rng.choice(len(AnomalyType)) + 1)
            return True, self._anomaly_type

        return False, None

    # ── Public API ────────────────────────────────────────────────────────

    def next(self) -> dict:
        phase = self._phase
        is_anomaly, atype = self._tick_anomaly()

        p_exp    = self._p_expected(phase)
        flow_exp = self._flow_expected(phase)
        ts_exp   = self._specimen_temp_expected(phase)

        pressure      = p_exp + float(self.rng.normal(0, p_exp * self.P_NOISE_REL + self.P_NOISE_FLOOR))
        temperature   = float(self.rng.normal(self.T_MEAN + self.T_P_COEFF * p_exp, self.T_STD))
        flow          = float(abs(self.rng.normal(flow_exp, self.F_STD)))
        specimen_temp = float(self.rng.normal(ts_exp, self.T_SPEC_STD))

        if is_anomaly:
            if atype == AnomalyType.PRESSURE_DROP:
                pressure -= float(self.rng.uniform(0.15, 0.40)) * self.P_MAX
            elif atype == AnomalyType.OVERPRESSURE:
                pressure += float(self.rng.uniform(0.06, 0.12)) * self.P_MAX
            elif atype == AnomalyType.THERMAL:
                temperature += float(self.rng.uniform(28.0, 50.0))
            elif atype == AnomalyType.FLOW_SPIKE:
                flow += float(self.rng.uniform(8.0, 22.0))
            elif atype == AnomalyType.UNDERCOOLING:
                specimen_temp -= float(self.rng.uniform(10.0, 20.0))

        prev_phase = self._phase
        self._step += 1
        if self._phase < prev_phase:
            self._cycle_count += 1

        return {
            "pressure":      round(max(0.0, pressure), 1),
            "temperature":   round(temperature, 1),
            "flow":          round(max(0.0, flow), 3),
            "specimen_temp": round(specimen_temp, 1),
            "cycle_phase":   round(phase, 4),
            "cycle_count":   self._cycle_count,
            "timestamp":     int(time.time() * 1000),
            "injected_anomaly": bool(is_anomaly),
            "anomaly_type":  atype.name if atype else None,
        }

    def generate_normal_data(self, n_cycles: int = 80) -> np.ndarray:
        """Full piston-compressor cycles for model training — no anomalies."""
        rng = np.random.default_rng(42)
        rows = []
        for _ in range(n_cycles):
            for step in range(self.CYCLE_STEPS):
                phase = step / self.CYCLE_STEPS
                p_exp = self._p_expected(phase)
                pressure      = p_exp + rng.normal(0, p_exp * self.P_NOISE_REL + self.P_NOISE_FLOOR)
                temperature   = rng.normal(self.T_MEAN + self.T_P_COEFF * p_exp, self.T_STD)
                flow          = abs(rng.normal(self._flow_expected(phase), self.F_STD))
                specimen_temp = rng.normal(self._specimen_temp_expected(phase), self.T_SPEC_STD)
                rows.append([pressure, temperature, flow, specimen_temp, phase])
        return np.array(rows)
