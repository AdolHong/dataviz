def transform(context):
    assert context.query_inputs["batch"] == 3
    rows = context.inputs["rows"]
    factor = context.compute_params["factor"]
    return {
        "main": [
            {"name": row["name"], "value": row["value"] * factor}
            for row in rows
        ]
    }
