"""애플리케이션 전역 상수 및 Enum 정의."""

from enum import Enum


class DeviceType(str, Enum):
    GRID_METER = "grid_meter"
    ESS = "ess"
    CHARGER = "charger"


class SensorType(str, Enum):
    GRID_CURRENT = "grid_current"
    ESS_SOC = "ess_soc"
    CHARGER_CURRENT = "charger_current"


class AlertType(str, Enum):
    PEAK_DETECTED = "peak_detected"
    PEAK_SHAVING_ACTIVATED = "peak_shaving_activated"
    PEAK_RESOLVED = "peak_resolved"


class AlertSeverity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"


class ControlAction(str, Enum):
    DISCHARGE = "discharge"
    CHARGE = "charge"
    STANDBY = "standby"


class TriggerSource(str, Enum):
    AI_AUTO = "ai_auto"
    MANUAL = "manual"


class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    VIEWER = "viewer"
