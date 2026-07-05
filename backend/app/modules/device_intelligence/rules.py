from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class DeviceRiskEvaluation:
    score: int
    risk_level: str
    decision: str
    reasons: list[str]
    evidence: dict[str, Any]
    adapter_mode: str = "RULE_BASED"


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _parse_major_version(version: str | None) -> int | None:
    if not version:
        return None
    major = ""
    for char in version:
        if char.isdigit():
            major += char
        else:
            break
    return int(major) if major else None


def _extract_latest(history: Any) -> Any:
    if history is None:
        return None
    if isinstance(history, dict):
        return history.get("latest_trusted_device") or history.get("latest_device")
    if isinstance(history, list):
        return history[0] if history else None
    return history


def _device_attr(device: Any, name: str, default: Any = None) -> Any:
    if device is None:
        return default
    if isinstance(device, dict):
        return device.get(name, default)
    return getattr(device, name, default)


def _risk_level(score: int) -> str:
    if score <= 29:
        return "LOW"
    if score <= 59:
        return "MEDIUM"
    if score <= 79:
        return "HIGH"
    return "CRITICAL"


def _decision(risk_level: str) -> str:
    mapping = {
        "LOW": "ALLOW_PIN",
        "MEDIUM": "REQUIRE_OTP",
        "HIGH": "REQUIRE_STEP_UP",
        "CRITICAL": "DENY_PIN",
    }
    return mapping[risk_level]


def evaluate_device_risk(current_device: Any, history: Any) -> dict[str, Any]:
    latest = _extract_latest(history)
    reasons: list[str] = []
    evidence: dict[str, Any] = {
        "current": {
            "device_id": _device_attr(current_device, "device_id"),
            "brand": _device_attr(current_device, "brand"),
            "model": _device_attr(current_device, "model"),
            "os_name": _device_attr(current_device, "os_name"),
            "os_version": _device_attr(current_device, "os_version"),
            "country": _device_attr(current_device, "country"),
            "city": _device_attr(current_device, "city"),
            "is_rooted": _device_attr(current_device, "is_rooted", False),
            "is_emulator": _device_attr(current_device, "is_emulator", False),
            "is_vpn": _device_attr(current_device, "is_vpn", False),
            "is_proxy": _device_attr(current_device, "is_proxy", False),
        },
        "history": None if latest is None else {
            "device_id": _device_attr(latest, "device_id"),
            "brand": _device_attr(latest, "brand"),
            "model": _device_attr(latest, "model"),
            "os_name": _device_attr(latest, "os_name"),
            "os_version": _device_attr(latest, "os_version"),
            "country": _device_attr(latest, "country"),
            "city": _device_attr(latest, "city"),
            "status": _device_attr(latest, "status"),
        },
    }

    is_rooted = bool(_device_attr(current_device, "is_rooted", False))
    is_emulator = bool(_device_attr(current_device, "is_emulator", False))
    is_vpn = bool(_device_attr(current_device, "is_vpn", False))
    is_proxy = bool(_device_attr(current_device, "is_proxy", False))

    if is_rooted and is_emulator:
        reasons.append("Device is rooted and running on an emulator.")
        return asdict(
            DeviceRiskEvaluation(
                score=100,
                risk_level="CRITICAL",
                decision="DENY_PIN",
                reasons=reasons,
                evidence={**evidence, "kill_switch": "rooted_and_emulator"},
            )
        )

    score = 0

    if is_rooted:
        score += 40
        reasons.append("Rooted device detected.")
    if is_emulator:
        score += 45
        reasons.append("Emulator detected.")
    if is_vpn:
        score += 20
        reasons.append("VPN detected.")
    if is_proxy:
        score += 20
        reasons.append("Proxy detected.")

    if latest is None:
        reasons.append("No trusted device history found.")
    else:
        current_brand = _normalize(_device_attr(current_device, "brand"))
        current_model = _normalize(_device_attr(current_device, "model"))
        current_country = _normalize(_device_attr(current_device, "country"))
        current_city = _normalize(_device_attr(current_device, "city"))
        current_os_name = _normalize(_device_attr(current_device, "os_name"))
        current_os_version = _device_attr(current_device, "os_version")
        current_device_id = _normalize(_device_attr(current_device, "device_id"))

        latest_brand = _normalize(_device_attr(latest, "brand"))
        latest_model = _normalize(_device_attr(latest, "model"))
        latest_country = _normalize(_device_attr(latest, "country"))
        latest_city = _normalize(_device_attr(latest, "city"))
        latest_os_name = _normalize(_device_attr(latest, "os_name"))
        latest_os_version = _device_attr(latest, "os_version")
        latest_device_id = _normalize(_device_attr(latest, "device_id"))

        if current_device_id and latest_device_id and current_device_id != latest_device_id:
            score += 30
            reasons.append("New device detected.")

        if current_brand and latest_brand and current_brand != latest_brand:
            score += 25
            reasons.append("Device brand changed.")
        if current_model and latest_model and current_model != latest_model:
            score += 20
            reasons.append("Device model changed.")
        if current_country and latest_country and current_country != latest_country:
            score += 25
            reasons.append("Country changed.")
        if current_city and latest_city and current_city != latest_city:
            score += 10
            reasons.append("City changed.")
        if current_os_name and latest_os_name and current_os_name != latest_os_name:
            score += 10
            reasons.append("Operating system changed.")
        else:
            current_major = _parse_major_version(current_os_version)
            latest_major = _parse_major_version(latest_os_version)
            if current_major is not None and latest_major is not None and abs(current_major - latest_major) >= 2:
                score += 10
                reasons.append("Operating system version changed significantly.")

        if is_vpn and current_country and latest_country and current_country != latest_country:
            score = max(score, 60)
            reasons.append("VPN active with country change.")

    if is_rooted or is_emulator:
        score = max(score, 80)
    if is_rooted and is_emulator:
        score = 100

    score = min(score, 100)
    risk_level = _risk_level(score)
    decision = _decision(risk_level)

    evidence["score_components"] = {
        "rooted": is_rooted,
        "emulator": is_emulator,
        "vpn": is_vpn,
        "proxy": is_proxy,
        "trusted_history_found": latest is not None,
    }

    return asdict(
        DeviceRiskEvaluation(
            score=score,
            risk_level=risk_level,
            decision=decision,
            reasons=reasons,
            evidence=evidence,
        )
    )
