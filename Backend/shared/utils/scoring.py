def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def risk_level_from_score(score: float) -> str:
    if score < 30:
        return "low"
    if score < 60:
        return "moderate"
    if score < 80:
        return "high"
    return "critical"
