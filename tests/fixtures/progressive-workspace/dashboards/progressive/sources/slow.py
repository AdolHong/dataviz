import time


def load(context):
    time.sleep(8)
    return [{"branch": "slow-ready", "value": 2}]
