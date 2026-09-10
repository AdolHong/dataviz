"""Deterministic synthetic sales, shared only inside this Dashboard.

No network, credentials, current date or random seed: identical inputs produce
identical data. This is a teaching fixture, not a holiday forecasting model.
"""

import math

import pandas as pd


CATEGORIES = {"水果": (320, 0.65, -1), "烘焙": (210, 0.95, 0), "饮料": (270, 0.35, 2)}
DAILY_COLUMNS = ["year", "year_label", "category", "relative_day", "actual_qty", "baseline_qty"]
SUMMARY_COLUMNS = ["year", "category", "actual_qty", "baseline_qty", "net_uplift_qty", "uplift_pct"]


def load(context):
    parameters = context.query_inputs
    if "year" in parameters:
        years = [parameters["year"]]
        categories = list(CATEGORIES)
    else:
        years = sorted(set(parameters["years"]))
        categories = [parameters["category"]]
    if any(year not in range(2023, 2027) for year in years):
        raise ValueError("模拟数据仅支持 2023–2026 年。")
    if any(category not in CATEGORIES for category in categories):
        raise ValueError("模拟品类仅支持水果、烘焙、饮料。")

    daily = []
    summary = []
    for year in years:
        for category in categories:
            base, strength, peak = CATEGORIES[category]
            actual_total = baseline_total = 0
            for day in range(-7, 8):
                baseline = round(base * (1 + 0.08 * (year - 2023)) * (1 + 0.04 * math.cos(day)))
                uplift = strength * math.exp(-((day - peak) / 2.8) ** 2)
                actual = round(baseline * (1 + uplift + 0.015 * (year - 2023) * math.sin(day)))
                daily.append([year, str(year), category, day, actual, baseline])
                actual_total += actual
                baseline_total += baseline
            net = actual_total - baseline_total
            summary.append([year, category, actual_total, baseline_total, net,
                            round(net / baseline_total * 100, 2)])
    # Explicit columns also make an empty year selection a valid empty table.
    return {"main": pd.DataFrame(summary, columns=SUMMARY_COLUMNS),
            "daily": pd.DataFrame(daily, columns=DAILY_COLUMNS)}
