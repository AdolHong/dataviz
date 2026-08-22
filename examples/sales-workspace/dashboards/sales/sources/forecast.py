def load(context):
    frame = context.table("orders").copy()
    frame["forecast_revenue"] = frame["revenue"] * 1.08
    return frame[["date", "region", "forecast_revenue"]]
