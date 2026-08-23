__all__ = [
    "Executor",
    "InteractionExecutor",
    "InteractionResult",
    "NodeResult",
    "RunResult",
    "resolve_compute_parameters",
    "resolve_query_parameters",
]


def __getattr__(name: str):
    if name in {"Executor", "resolve_query_parameters"}:
        from dataviz.execution.executor import Executor, resolve_query_parameters

        return {
            "Executor": Executor,
            "resolve_query_parameters": resolve_query_parameters,
        }[name]
    if name in {"InteractionResult", "NodeResult", "RunResult"}:
        from dataviz.execution.results import InteractionResult, NodeResult, RunResult

        return {
            "InteractionResult": InteractionResult,
            "NodeResult": NodeResult,
            "RunResult": RunResult,
        }[name]
    if name in {"InteractionExecutor", "resolve_compute_parameters"}:
        from dataviz.execution.interactive import (
            InteractionExecutor,
            resolve_compute_parameters,
        )

        return {
            "InteractionExecutor": InteractionExecutor,
            "resolve_compute_parameters": resolve_compute_parameters,
        }[name]
    raise AttributeError(name)
