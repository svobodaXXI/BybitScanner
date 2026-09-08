from app.core.monitoring.enums import MonitoringStatus


def test_monitoring_status_values() -> None:
    assert {item.value for item in MonitoringStatus} == {"ACTIVE", "EXPIRED"}

