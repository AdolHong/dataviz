def transform(context):
    orders = context.table("orders").copy()
    targets = context.table("targets").copy()

    trend = orders[["date", "region", "revenue"]].copy()
    trend["forecast_revenue"] = trend["revenue"] * 1.08

    completion = (
        orders.groupby("region", as_index=False)["revenue"]
        .sum()
        .merge(targets, on="region", how="left")
    )
    completion["completion_pct"] = (
        completion["revenue"] / completion["target"] * 100
    ).round(2)
    return {"trend": trend, "completion": completion}
