DEFAULT_WEIGHTS = {
    "SSCS-001": 0.7,
    "SSCS-002": 0.6,
    "SSCS-003": 0.8,
    "SSCS-004": 0.7,
    "SSCS-005": 0.5,
    "SSCS-006": 0.9,
    "SSCS-CHAIN": 0.95,
    "SSCS-DORM": 0.55,
}
DEFAULT_THRESHOLDS = {
    "SSCS-001": {"max_distance": 2},
    "SSCS-002": {"burst_count": 7, "window_days": 7, "interval_ratio": 0.25},
    "SSCS-005": {"night_hours": [0, 1, 2, 3, 4, 5, 6, 23], "warmup": 10},
    "SSCS-006": {"min_packages": 3, "max_followers": 5},
}
SEV_BOUNDS = {"critical": 0.9, "high": 0.7, "medium": 0.4}
DEDUP_WINDOW_DAYS = 7
