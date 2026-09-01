__all__ = [
    "Executor",
    "InteractionExecutor",
    "InteractionResult",
    "NodeResult",
    "RunResult",
    "resolve_control_states",
    "resolve_dashboard_query_parameter_state",
]


def __getattr__(name: str):
    if name in {"Executor", "resolve_dashboard_query_parameter_state"}:
        from dataviz.execution.executor import (
            Executor,
            resolve_dashboard_query_parameter_state,
        )

        return {
            "Executor": Executor,
            "resolve_dashboard_query_parameter_state": resolve_dashboard_query_parameter_state,
        }[name]
    if name in {"InteractionResult", "NodeResult", "RunResult"}:
        from dataviz.execution.results import InteractionResult, NodeResult, RunResult

        return {
            "InteractionResult": InteractionResult,
            "NodeResult": NodeResult,
            "RunResult": RunResult,
        }[name]
    if name in {"InteractionExecutor", "resolve_control_states"}:
        from dataviz.execution.interactive import InteractionExecutor
        from dataviz.workspace.controls import resolve_control_states

        return {
            "InteractionExecutor": InteractionExecutor,
            "resolve_control_states": resolve_control_states,
        }[name]
    raise AttributeError(name)
