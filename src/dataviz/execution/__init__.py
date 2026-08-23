__all__ = ["Executor", "NodeResult", "RunResult", "resolve_parameters"]


def __getattr__(name: str):
    if name in {"Executor", "resolve_parameters"}:
        from dataviz.execution.executor import Executor, resolve_parameters

        return {"Executor": Executor, "resolve_parameters": resolve_parameters}[name]
    if name in {"NodeResult", "RunResult"}:
        from dataviz.execution.results import NodeResult, RunResult

        return {"NodeResult": NodeResult, "RunResult": RunResult}[name]
    raise AttributeError(name)
