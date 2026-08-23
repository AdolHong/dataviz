from __future__ import annotations

import math
import pandas as pd


def load(context):
    rows = []
    for day in range(1, 6):
        for hour in range(9, 23):
            baseline = 420 + 680 * math.sin((hour - 9) / 13 * math.pi)
            actual = round(baseline * (0.88 + day * 0.035) + ((hour * day) % 7) * 24)
            forecast = round(baseline * (0.94 + day * 0.028))
            rows.append({
                "day": f"2025-10-{day:02d}",
                "hour": hour,
                "timestamp": f"2025-10-{day:02d}T{hour:02d}:00:00",
                "actual": actual,
                "forecast": forecast,
                "error": abs(actual - forecast),
            })
    return pd.DataFrame(rows)
