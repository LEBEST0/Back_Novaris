from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import time
from statistics import fmean, pstdev
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _bounded(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass(slots=True)
class _SessionWindow:
    started_ms: float | None = None
    ended_ms: float | None = None


class MockBehaviouralSDKCollector:
    def __init__(
        self,
        *,
        sdk_version: str = "1.0.0",
        payload_version: str = "v1",
        platform: str = "WEB_MOCK",
    ) -> None:
        self.sdk_version = sdk_version
        self.payload_version = payload_version
        self.platform = platform
        self.reset()

    def _now_ms(self) -> float:
        return time.time() * 1000.0

    def start_session(self, timestamp_ms: float | None = None) -> None:
        self._session.started_ms = timestamp_ms if timestamp_ms is not None else self._now_ms()
        self._session.ended_ms = None

    def end_session(self, timestamp_ms: float | None = None) -> float:
        end_ms = timestamp_ms if timestamp_ms is not None else self._now_ms()
        if self._session.started_ms is None:
            self._session.started_ms = end_ms
        self._session.ended_ms = end_ms
        duration = max(0.0, self._session.ended_ms - self._session.started_ms)
        self._session_durations_ms.append(duration)
        return duration

    def start_action(self, action_type: str, timestamp_ms: float | None = None) -> None:
        self._current_action = action_type
        self._current_action_started_ms = timestamp_ms if timestamp_ms is not None else self._now_ms()

    def end_action(self, action_type: str, timestamp_ms: float | None = None) -> float:
        end_ms = timestamp_ms if timestamp_ms is not None else self._now_ms()
        if self._current_action != action_type or self._current_action_started_ms is None:
            return 0.0
        duration = max(0.0, end_ms - self._current_action_started_ms)
        self._action_durations_ms.append(duration)
        self._current_action = None
        self._current_action_started_ms = None
        return duration

    def record_key_press(self, timestamp_ms: float | None = None) -> None:
        self._key_press_times_ms.append(timestamp_ms if timestamp_ms is not None else self._now_ms())

    def record_touch_down(self, timestamp_ms: float | None = None, pressure: float | None = None) -> None:
        self._current_touch_down_ms = timestamp_ms if timestamp_ms is not None else self._now_ms()
        if pressure is not None:
            self._touch_pressures.append(float(pressure))

    def record_touch_up(self, timestamp_ms: float | None = None, pressure: float | None = None) -> float:
        up_ms = timestamp_ms if timestamp_ms is not None else self._now_ms()
        if self._current_touch_down_ms is None:
            return 0.0
        duration = max(0.0, up_ms - self._current_touch_down_ms)
        self._touch_durations_ms.append(duration)
        if pressure is not None:
            self._touch_pressures.append(float(pressure))
        self._current_touch_down_ms = None
        return duration

    def record_error(self) -> None:
        self._error_count += 1

    def record_correction(self) -> None:
        self._correction_count += 1

    def _avg_key_interval_ms(self) -> float | None:
        if len(self._key_press_times_ms) < 2:
            return None
        intervals = [
            self._key_press_times_ms[index] - self._key_press_times_ms[index - 1]
            for index in range(1, len(self._key_press_times_ms))
        ]
        return fmean(intervals)

    def _typing_speed_cps(self) -> float:
        if len(self._key_press_times_ms) < 2:
            return 0.0
        interval_ms = self._avg_key_interval_ms() or 0.0
        if interval_ms <= 0:
            return 0.0
        return 1000.0 / interval_ms

    def _avg_touch_duration_ms(self) -> float | None:
        if not self._touch_durations_ms:
            return None
        return fmean(self._touch_durations_ms)

    def _tap_pressure_avg(self) -> float | None:
        if not self._touch_pressures:
            return None
        return fmean(self._touch_pressures)

    def _tap_pressure_std(self) -> float | None:
        if len(self._touch_pressures) < 2:
            return 0.0 if self._touch_pressures else None
        return pstdev(self._touch_pressures)

    def _hesitation_time_ms(self) -> float:
        if not self._action_durations_ms:
            return 0.0
        return fmean(self._action_durations_ms)

    def _swipe_speed_avg(self) -> float:
        session_duration = self._session_duration_ms()
        if session_duration <= 0:
            return 0.0
        return len(self._action_durations_ms) * 1000.0 / session_duration

    def _touch_precision_score(self) -> float:
        penalty = (self._error_count * 0.05) + (self._correction_count * 0.02)
        if self._touch_pressures:
            pressure_std = self._tap_pressure_std() or 0.0
            penalty += min(0.2, pressure_std * 0.1)
        return _bounded(1.0 - penalty, 0.0, 1.0)

    def _session_duration_ms(self) -> float:
        if self._session.started_ms is None:
            return 0.0
        end_ms = self._session.ended_ms if self._session.ended_ms is not None else self._now_ms()
        return max(0.0, end_ms - self._session.started_ms)

    def build_payload(self, user_id: str, session_id: str, action_type: str) -> dict[str, Any]:
        timestamp = _utcnow().isoformat()
        request_id = str(uuid4())
        nonce = str(uuid4())
        return {
            "user_id": user_id,
            "session_id": session_id,
            "action_type": action_type,
            "request_id": request_id,
            "timestamp": timestamp,
            "nonce": nonce,
            "sdk_version": self.sdk_version,
            "payload_version": self.payload_version,
            "platform": self.platform,
            "avg_key_interval_ms": self._avg_key_interval_ms(),
            "avg_touch_duration_ms": self._avg_touch_duration_ms(),
            "typing_speed_cps": self._typing_speed_cps(),
            "tap_pressure_avg": self._tap_pressure_avg(),
            "tap_pressure_std": self._tap_pressure_std(),
            "error_count": self._error_count,
            "correction_count": self._correction_count,
            "hesitation_time_ms": self._hesitation_time_ms(),
            "swipe_speed_avg": self._swipe_speed_avg(),
            "touch_precision_score": self._touch_precision_score(),
            "device_orientation_changes": self._device_orientation_changes,
            "session_duration_ms": self._session_duration_ms(),
        }

    def reset(self) -> None:
        self._session = _SessionWindow()
        self._current_action: str | None = None
        self._current_action_started_ms: float | None = None
        self._current_touch_down_ms: float | None = None
        self._key_press_times_ms: list[float] = []
        self._touch_durations_ms: list[float] = []
        self._touch_pressures: list[float] = []
        self._action_durations_ms: list[float] = []
        self._session_durations_ms: list[float] = []
        self._error_count = 0
        self._correction_count = 0
        self._device_orientation_changes = 0


def build_signed_request(
    user_id: str,
    session_id: str,
    action_type: str,
    client_key: str,
    signature_secret: str,
) -> dict[str, Any]:
    collector = MockBehaviouralSDKCollector()
    collector.start_session()
    payload = collector.build_payload(user_id=user_id, session_id=session_id, action_type=action_type)
    canonical_payload = _canonical_json(payload)
    signature = hmac.new(
        signature_secret.encode("utf-8"),
        canonical_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "payload": payload,
        "headers": {
            "X-Novaris-Client-Key": client_key,
            "X-Novaris-Signature": signature,
        },
    }
