from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from dataviz.filesystem import atomic_write_text, transactional_write_texts


AUTHORING_EVALUATION_SCHEMA = "dataviz/authoring-evaluation/v2"
AUTHORING_TASK_CATALOG_SCHEMA = "dataviz/authoring-task-catalog/v2"
AUTHORING_TRIAL_SCHEMA = "dataviz/authoring-trial/v2"
AUTHORING_ASSESSMENT_SCHEMA = "dataviz/authoring-assessment/v1"
AUTHORING_APPROACHES = ("dataviz", "standalone-html")
AUTHORING_ASSESSMENT_STATUSES = ("passed", "failed", "unmeasured")
AUTHORING_ASSESSORS = ("human", "automation", "mixed")


AUTHORING_TASK_FIXTURES: dict[str, dict[str, str]] = {
    "default-dashboard": {
        "data/sales.csv": """date,region,revenue,orders
2026-01-01,North,120,12
2026-01-01,South,90,9
2026-02-01,North,150,14
2026-02-01,South,110,11
2026-03-01,North,170,15
2026-03-01,South,130,13
""",
    },
    "three-level-selection": {
        "data/geography.csv": """province,city,district,value
Guangdong,Shenzhen,Nanshan,84
Guangdong,Shenzhen,Futian,71
Guangdong,Foshan,Shunde,66
Guangdong,Foshan,Sanshui,48
Fujian,Xiamen,Siming,79
Fujian,Xiamen,Huli,68
Fujian,Quanzhou,Licheng,52
Fujian,Quanzhou,Fengze,43
""",
    },
    "dataset-multi-output": {
        "data/orders.csv": """order_id,store_id,amount
O001,S001,120
O002,S001,80
O003,S002,150
O004,S003,90
""",
        "data/stores.csv": """store_id,region,target
S001,North,180
S002,South,140
S003,East,100
""",
    },
    "interactive-runtime-matrix": {
        "data/base.csv": """name,value
alpha,1
beta,2
gamma,3
""",
    },
    "custom-renderer": {
        "data/nodes.csv": """id,label,group,score
A,Alpha,Core,82
B,Beta,Core,71
C,Gamma,Edge,64
D,Delta,Edge,58
""",
        "data/edges.csv": """source,target,weight
A,B,8
A,C,5
B,D,4
C,D,7
""",
    },
}


AUTHORING_TASKS: dict[str, dict[str, Any]] = {
    "default-dashboard": {
        "title": "Default declarative Dashboard",
        "purpose": "Measure the shortest normal path without custom Canvas code.",
        "brief": (
            "Using the supplied sales rows, build a metric, a monthly revenue line chart "
            "and a detail table. Add a date Query Parameter and a region include Selection."
        ),
        "acceptance": [
            {
                "id": "state-boundary",
                "criterion": "The query state and browser Selection have different commit behavior.",
            },
            {
                "id": "cross-view-consistency",
                "criterion": "Metric, chart and table agree after changing the Selection.",
            },
            {
                "id": "interactive-export",
                "criterion": "The result exports and opens as an interactive report.",
            },
            {
                "id": "no-custom-page-code",
                "criterion": "No custom page HTML/CSS/JavaScript is required by the Dataviz variant.",
            },
        ],
        "dataviz_focus": ["dashboard", "view.line", "view.table", "control.select"],
    },
    "three-level-selection": {
        "title": "Three scopes and path cascade",
        "purpose": "Measure whether Selection scope and cascade contracts prevent retries.",
        "brief": (
            "Build a province Dashboard Selection Control, a city Section Selection Control and a province/city/"
            "district View cascader. Upstream changes must reconcile invalid downstream values."
        ),
        "acceptance": [
            {
                "id": "scope-boundary",
                "criterion": "Dashboard, Section and View scope affect only their declared Views.",
            },
            {
                "id": "cascade-reconciliation",
                "criterion": "Province changes immediately update city and district domains.",
            },
            {
                "id": "view-isolation",
                "criterion": "A View-scoped Selection Control does not redraw an unrelated sibling View.",
            },
            {
                "id": "overlay-export-parity",
                "criterion": "Outside click, Escape, search and exported HTML behavior are consistent.",
            },
        ],
        "dataviz_focus": ["selections", "control.cascader", "runtime.overlay"],
    },
    "dataset-multi-output": {
        "title": "Complex Dataset Transform with Named Outputs",
        "purpose": "Measure Server data-pipeline authoring and boundary diagnostics.",
        "brief": (
            "Join two supplied Sources in one server Dataset Transform and emit a typed detail "
            "table, scalar total and metadata object, then bind each Named Output to a View."
        ),
        "acceptance": [
            {
                "id": "explicit-contracts",
                "criterion": "The transform declares explicit inputs, input schemas and three Named Outputs.",
            },
            {
                "id": "progressive-branch",
                "criterion": "A fast independent Source/View can render before this branch completes.",
            },
            {
                "id": "boundary-diagnostics",
                "criterion": "Validation and runtime failures identify the exact schema/output boundary.",
            },
            {
                "id": "committed-export",
                "criterion": "The exported report contains the committed Base Outputs.",
            },
        ],
        "dataviz_focus": ["pipeline", "dataset-transform.server-python", "validation"],
    },
    "interactive-runtime-matrix": {
        "title": "Interactive Runtime matrix",
        "purpose": "Measure Runtime/export choices without conflating them with data loading.",
        "brief": (
            "From one immutable Base Output, implement a Compute Control consumed by browser-js, "
            "and server-python branches. Show their Derived Outputs side by side."
        ),
        "acceptance": [
            {
                "id": "no-query-rerun",
                "criterion": "Changing Compute does not create a Query Run or re-read a Source.",
            },
            {
                "id": "branch-isolation",
                "criterion": "Each branch has timeout/error state and does not redraw unrelated Views.",
            },
            {
                "id": "browser-export",
                "criterion": "browser-js remains interactive in export.",
            },
            {
                "id": "server-export-boundary",
                "criterion": "server-python is explicitly snapshot or unavailable in export.",
            },
        ],
        "dataviz_focus": ["interactive-transforms", "browser-js", "server-python", "export"],
    },
    "custom-renderer": {
        "title": "Custom Renderer escape hatch",
        "purpose": "Measure how much context/code a genuinely custom visual needs.",
        "brief": (
            "Create a custom visual Renderer for a supplied Named Output, with local styles and "
            "empty/error behavior, while retaining the default Dashboard shell and controls."
        ),
        "acceptance": [
            {
                "id": "renderer-lifecycle",
                "criterion": "The Renderer implements validate, mount, update and dispose.",
            },
            {
                "id": "public-contract",
                "criterion": "It consumes only the public Runtime descriptor/context contract.",
            },
            {
                "id": "scoped-css",
                "criterion": "Its CSS is scoped and does not break default Views or overlays.",
            },
            {
                "id": "export-parity",
                "criterion": "Server and exported HTML use the same implementation.",
            },
        ],
        "dataviz_focus": ["renderer.custom", "frontend-adapters", "components"],
    },
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(payload)


def _task_contract(task_id: str) -> dict[str, Any]:
    definition = AUTHORING_TASKS[task_id]
    fixture_hashes = {
        path: _sha256_text(content)
        for path, content in sorted(AUTHORING_TASK_FIXTURES[task_id].items())
    }
    return {
        "benchmark_task": task_id,
        "title": definition["title"],
        "brief": definition["brief"],
        "acceptance": definition["acceptance"],
        "files": fixture_hashes,
    }


def _task_contract_sha256(task_id: str) -> str:
    return _canonical_sha256(_task_contract(task_id))


def _fixture_sha256(files: dict[str, str]) -> str:
    return _canonical_sha256({path: files[path] for path in sorted(files)})


def _approach_constraint(approach: str) -> str:
    if approach == "dataviz":
        return (
            "Use the installed Dataviz CLI and current DSL. Begin with `dataviz docs`, "
            "and do not copy a prebuilt Dashboard."
        )
    return (
        "Build a standalone HTML implementation. "
        "Do not import or generate code from Dataviz."
    )


def _task_markdown(task_id: str, approach: str, files: dict[str, str]) -> str:
    definition = AUTHORING_TASKS[task_id]
    return "\n".join(
        [
            f"# {definition['title']}",
            "",
            definition["brief"],
            "",
            f"Approach constraint: {_approach_constraint(approach)}",
            "",
            "## Acceptance",
            "",
            *[
                f"- [{item['id']}] {item['criterion']}"
                for item in definition["acceptance"]
            ],
            "",
            "## Inputs",
            "",
            *[f"- `{name}`" for name in sorted(files)],
            "",
        ]
    )


def authoring_task_catalog(task_id: str | None = None) -> dict[str, Any]:
    if task_id is not None and task_id not in AUTHORING_TASKS:
        raise ValueError(
            f"Unknown authoring evaluation task: {task_id}. "
            f"Available: {', '.join(AUTHORING_TASKS)}"
        )
    tasks = (
        {task_id: AUTHORING_TASKS[task_id]}
        if task_id is not None
        else AUTHORING_TASKS
    )
    return {
        "schema": AUTHORING_TASK_CATALOG_SCHEMA,
        "tasks": {
            identifier: {"id": identifier, **definition}
            for identifier, definition in tasks.items()
        },
        "approaches": list(AUTHORING_APPROACHES),
    }


def authoring_evaluation_protocol(task_id: str | None = None) -> dict[str, Any]:
    catalog = authoring_task_catalog(task_id)
    return {
        "schema": AUTHORING_EVALUATION_SCHEMA,
        "tasks": catalog["tasks"],
        "paired_design": {
            "unit": "One task + one model/client + one trial_id + both approaches",
            "approaches": list(AUTHORING_APPROACHES),
            "order": "Alternate or randomize approach order across repeated trials.",
            "fresh_start": (
                "Use a fresh working copy and a fresh AI conversation for each approach; "
                "do not let one implementation reveal code to the other."
            ),
            "same_inputs": (
                "Use prepared trials with the same task-contract and fixture SHA-256, model, "
                "tool permissions and time budget. Each approach has one immutable, hashed "
                "constraint prompt. Dataviz may use installed CLI docs; standalone HTML may "
                "use its normal platform/library documentation."
            ),
        },
        "measurements": [
            "actual client-reported input tokens",
            "actual client-reported output tokens",
            "first-attempt success",
            "behavior-changing correction rounds",
            "elapsed wall time",
            "final outcome and categorized friction",
        ],
        "quality_gate": (
            "Count a success only when the fixed task prompt and inputs remain intact and every "
            "acceptance check records an assessor plus evidence and passes. A smaller answer "
            "that does not work is not an efficiency win."
        ),
        "token_rule": (
            "Never estimate model tokens from bytes or characters. Missing client measurements "
            "remain unmeasured."
        ),
        "commands": {
            "prepare": (
                "dataviz authoring prepare TASK DIRECTORY --approach "
                "dataviz|standalone-html --trial-id TRIAL"
            ),
            "start": (
                "dataviz authoring start WORKSPACE --trial-dir DIRECTORY "
                "--model MODEL --tool TOOL"
            ),
            "assess": (
                "dataviz authoring assess DIRECTORY CHECK --status passed "
                "--assessor human|automation|mixed --evidence \"...\""
            ),
            "verify": "dataviz authoring verify DIRECTORY --format json",
            "finish": (
                "dataviz authoring finish WORKSPACE SESSION --outcome success|partial|failed "
                "--first-attempt success|failure|unknown --correction-rounds N "
                "--trial-dir DIRECTORY [--input-tokens N --output-tokens N]"
            ),
            "compare": "dataviz authoring compare WORKSPACE --format json",
        },
    }


def prepare_authoring_trial(
    task_id: str,
    destination: Path,
    *,
    approach: str,
    trial_id: str,
) -> dict[str, Any]:
    """Create one neutral, reproducible task pack without implementing the result."""

    catalog = authoring_task_catalog(task_id)
    if approach not in AUTHORING_APPROACHES:
        raise ValueError(
            f"Unknown authoring approach: {approach}. "
            f"Available: {', '.join(AUTHORING_APPROACHES)}"
        )
    if not trial_id.strip():
        raise ValueError("trial_id cannot be empty")
    root = destination.resolve()
    if root.exists() and not root.is_dir():
        raise ValueError(f"Authoring trial destination is not a directory: {root}")
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"Authoring trial directory must be empty: {root}")
    definition = catalog["tasks"][task_id]
    fixture_files = AUTHORING_TASK_FIXTURES[task_id]
    files: dict[str, str] = {}
    for relative, content in fixture_files.items():
        files[relative] = hashlib.sha256(content.encode("utf-8")).hexdigest()

    task_markdown = _task_markdown(task_id, approach, files)
    task_contract_sha256 = _task_contract_sha256(task_id)
    task_prompt_sha256 = _sha256_text(task_markdown)
    fixture_sha256 = _fixture_sha256(files)
    manifest = {
        "schema": AUTHORING_TRIAL_SCHEMA,
        "benchmark_task": task_id,
        "approach": approach,
        "trial_id": trial_id.strip(),
        "task": definition["brief"],
        "acceptance": definition["acceptance"],
        "files": files,
        "task_contract_sha256": task_contract_sha256,
        "task_prompt_sha256": task_prompt_sha256,
        "fixture_sha256": fixture_sha256,
        "measurement_rule": (
            "Use a fresh AI session. Record actual client token usage; never estimate."
        ),
    }
    assessment = {
        "schema": AUTHORING_ASSESSMENT_SCHEMA,
        "benchmark_task": task_id,
        "approach": approach,
        "trial_id": trial_id.strip(),
        "checks": [
            {
                "id": item["id"],
                "status": "unmeasured",
                "assessor": None,
                "evidence": "",
            }
            for item in definition["acceptance"]
        ],
    }
    transactional_write_texts(
        root,
        {
            **fixture_files,
            "TASK.md": task_markdown,
            "trial.json": json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            "assessment.json": (
                json.dumps(assessment, ensure_ascii=False, indent=2) + "\n"
            ),
        },
    )
    return {**manifest, "directory": str(root)}


def inspect_authoring_trial(destination: Path) -> dict[str, Any]:
    """Verify one prepared trial without executing or trusting its solution."""

    root = destination.resolve()
    diagnostics: list[dict[str, Any]] = []

    def diagnostic(code: str, message: str, **details: Any) -> None:
        diagnostics.append({"code": code, "message": message, **details})

    manifest_path = root / "trial.json"
    assessment_path = root / "assessment.json"
    manifest: dict[str, Any] = {}
    assessment: dict[str, Any] = {}
    if not root.is_dir():
        diagnostic("authoring_trial_missing", "Trial directory does not exist")
    elif not manifest_path.is_file():
        diagnostic("authoring_trial_manifest_missing", "trial.json is missing")
    else:
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                manifest = value
            else:
                diagnostic(
                    "authoring_trial_manifest_invalid",
                    "trial.json must contain one JSON object",
                )
        except Exception as error:
            diagnostic(
                "authoring_trial_manifest_invalid",
                "trial.json is not valid JSON",
                error=str(error),
            )

    task_id = manifest.get("benchmark_task")
    approach = manifest.get("approach")
    trial_id = manifest.get("trial_id")
    expected_files: dict[str, str] = {}
    expected_contract_sha256: str | None = None
    expected_prompt_sha256: str | None = None
    expected_fixture_sha256: str | None = None
    if manifest:
        if manifest.get("schema") != AUTHORING_TRIAL_SCHEMA:
            diagnostic(
                "authoring_trial_schema_invalid",
                f"trial.json must use {AUTHORING_TRIAL_SCHEMA}",
                actual=manifest.get("schema"),
            )
        if task_id not in AUTHORING_TASKS:
            diagnostic(
                "authoring_trial_task_unknown",
                "Trial benchmark_task is unknown",
                actual=task_id,
                available=sorted(AUTHORING_TASKS),
            )
        else:
            contract = _task_contract(task_id)
            expected_files = contract["files"]
            expected_contract_sha256 = _canonical_sha256(contract)
            expected_fixture_sha256 = _fixture_sha256(expected_files)
            if manifest.get("task") != contract["brief"]:
                diagnostic(
                    "authoring_trial_task_changed",
                    "Trial task text differs from the installed fixed task",
                )
            if manifest.get("acceptance") != contract["acceptance"]:
                diagnostic(
                    "authoring_trial_acceptance_changed",
                    "Trial acceptance contract differs from the installed fixed task",
                )
            if manifest.get("files") != expected_files:
                diagnostic(
                    "authoring_trial_file_manifest_changed",
                    "Trial fixture manifest differs from the installed fixed task",
                )
            if manifest.get("task_contract_sha256") != expected_contract_sha256:
                diagnostic(
                    "authoring_trial_contract_hash_mismatch",
                    "Trial task contract hash is invalid",
                    expected=expected_contract_sha256,
                    actual=manifest.get("task_contract_sha256"),
                )
            if manifest.get("fixture_sha256") != expected_fixture_sha256:
                diagnostic(
                    "authoring_trial_fixture_digest_mismatch",
                    "Trial aggregate fixture hash is invalid",
                    expected=expected_fixture_sha256,
                    actual=manifest.get("fixture_sha256"),
                )
        if approach not in AUTHORING_APPROACHES:
            diagnostic(
                "authoring_trial_approach_invalid",
                "Trial approach is invalid",
                actual=approach,
                available=list(AUTHORING_APPROACHES),
            )
        if not isinstance(trial_id, str) or not trial_id.strip():
            diagnostic("authoring_trial_id_invalid", "Trial id cannot be empty")

    if task_id in AUTHORING_TASKS and approach in AUTHORING_APPROACHES:
        expected_prompt = _task_markdown(task_id, approach, expected_files)
        expected_prompt_sha256 = _sha256_text(expected_prompt)
        if manifest.get("task_prompt_sha256") != expected_prompt_sha256:
            diagnostic(
                "authoring_trial_task_prompt_hash_mismatch",
                "Trial task prompt hash is invalid",
                expected=expected_prompt_sha256,
                actual=manifest.get("task_prompt_sha256"),
            )
        task_path = root / "TASK.md"
        actual_prompt_sha256 = (
            hashlib.sha256(task_path.read_bytes()).hexdigest()
            if task_path.is_file()
            else None
        )
        if actual_prompt_sha256 != expected_prompt_sha256:
            diagnostic(
                "authoring_trial_task_prompt_changed",
                "TASK.md is missing or differs from the fixed approach prompt",
                expected=expected_prompt_sha256,
                actual=actual_prompt_sha256,
            )

    actual_files: dict[str, str | None] = {}
    for relative, expected_hash in expected_files.items():
        target = root / relative
        actual_hash = (
            hashlib.sha256(target.read_bytes()).hexdigest()
            if target.is_file()
            else None
        )
        actual_files[relative] = actual_hash
        if actual_hash != expected_hash:
            diagnostic(
                "authoring_trial_fixture_changed",
                "Prepared input fixture is missing or changed",
                file=relative,
                expected=expected_hash,
                actual=actual_hash,
            )

    integrity_codes = {
        item["code"]
        for item in diagnostics
        if item["code"] != "authoring_trial_assessment_invalid"
    }
    integrity_passed = not integrity_codes

    if not assessment_path.is_file():
        diagnostic(
            "authoring_trial_assessment_invalid",
            "assessment.json is missing",
        )
    else:
        try:
            value = json.loads(assessment_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                assessment = value
            else:
                diagnostic(
                    "authoring_trial_assessment_invalid",
                    "assessment.json must contain one JSON object",
                )
        except Exception as error:
            diagnostic(
                "authoring_trial_assessment_invalid",
                "assessment.json is not valid JSON",
                error=str(error),
            )

    expected_checks = (
        AUTHORING_TASKS[task_id]["acceptance"] if task_id in AUTHORING_TASKS else []
    )
    expected_check_ids = [item["id"] for item in expected_checks]
    normalized_checks: list[dict[str, Any]] = []
    if assessment:
        if assessment.get("schema") != AUTHORING_ASSESSMENT_SCHEMA:
            diagnostic(
                "authoring_trial_assessment_invalid",
                f"assessment.json must use {AUTHORING_ASSESSMENT_SCHEMA}",
            )
        for field, expected in (
            ("benchmark_task", task_id),
            ("approach", approach),
            ("trial_id", trial_id),
        ):
            if assessment.get(field) != expected:
                diagnostic(
                    "authoring_trial_assessment_invalid",
                    f"assessment.json {field} does not match trial.json",
                    field=field,
                )
        raw_checks = assessment.get("checks")
        if not isinstance(raw_checks, list):
            diagnostic(
                "authoring_trial_assessment_invalid",
                "assessment.json checks must be a list",
            )
            raw_checks = []
        actual_check_ids = [
            item.get("id") for item in raw_checks if isinstance(item, dict)
        ]
        if actual_check_ids != expected_check_ids:
            diagnostic(
                "authoring_trial_assessment_invalid",
                "Assessment check ids/order differ from the fixed acceptance contract",
                expected=expected_check_ids,
                actual=actual_check_ids,
            )
        for item in raw_checks:
            if not isinstance(item, dict):
                diagnostic(
                    "authoring_trial_assessment_invalid",
                    "Every assessment check must be an object",
                )
                continue
            check_id = item.get("id")
            status = item.get("status")
            assessor = item.get("assessor")
            evidence = item.get("evidence")
            if status not in AUTHORING_ASSESSMENT_STATUSES:
                diagnostic(
                    "authoring_trial_assessment_invalid",
                    f"Assessment {check_id!r} has an invalid status",
                )
                continue
            if status == "unmeasured":
                if assessor is not None or evidence not in {"", None}:
                    diagnostic(
                        "authoring_trial_assessment_invalid",
                        f"Unmeasured assessment {check_id!r} cannot claim evidence",
                    )
            elif assessor not in AUTHORING_ASSESSORS or not isinstance(
                evidence, str
            ) or not evidence.strip():
                diagnostic(
                    "authoring_trial_assessment_invalid",
                    f"Measured assessment {check_id!r} requires assessor and evidence",
                )
            normalized_checks.append(
                {
                    "id": check_id,
                    "status": status,
                    "assessor": assessor,
                    "evidence": evidence.strip() if isinstance(evidence, str) else "",
                }
            )

    assessment_valid = not any(
        item["code"] == "authoring_trial_assessment_invalid"
        for item in diagnostics
    )
    quality_passed = (
        integrity_passed
        and assessment_valid
        and len(normalized_checks) == len(expected_check_ids)
        and all(item["status"] == "passed" for item in normalized_checks)
    )
    return {
        "schema": "dataviz/authoring-trial-check/v1",
        "directory": str(root),
        "benchmark_task": task_id,
        "approach": approach,
        "trial_id": trial_id,
        "task": manifest.get("task"),
        "task_contract_sha256": expected_contract_sha256,
        "task_prompt_sha256": expected_prompt_sha256,
        "fixture_sha256": expected_fixture_sha256,
        "actual_files": actual_files,
        "integrity_passed": integrity_passed,
        "assessment_valid": assessment_valid,
        "quality_passed": quality_passed,
        "checks": normalized_checks,
        "diagnostics": diagnostics,
    }


def record_authoring_assessment(
    destination: Path,
    check_id: str,
    *,
    status: str,
    assessor: str | None,
    evidence: str,
) -> dict[str, Any]:
    """Update one fixed acceptance check without changing trial inputs."""

    root = destination.resolve()
    report = inspect_authoring_trial(root)
    if not report["integrity_passed"] or not report["assessment_valid"]:
        raise ValueError(
            "Authoring trial is invalid; run `dataviz authoring verify` for diagnostics"
        )
    available = [item["id"] for item in report["checks"]]
    if check_id not in available:
        raise ValueError(
            f"Unknown acceptance check {check_id!r}; available: {', '.join(available)}"
        )
    if status not in AUTHORING_ASSESSMENT_STATUSES:
        raise ValueError(
            f"Invalid assessment status {status!r}; "
            f"available: {', '.join(AUTHORING_ASSESSMENT_STATUSES)}"
        )
    if status == "unmeasured":
        assessor = None
        evidence = ""
    elif assessor not in AUTHORING_ASSESSORS or not evidence.strip():
        raise ValueError(
            "passed/failed assessments require --assessor human|automation|mixed "
            "and non-empty --evidence"
        )
    path = root / "assessment.json"
    assessment = json.loads(path.read_text(encoding="utf-8"))
    for item in assessment["checks"]:
        if item["id"] == check_id:
            item.update(
                {
                    "status": status,
                    "assessor": assessor,
                    "evidence": evidence.strip(),
                }
            )
            break
    atomic_write_text(
        path,
        json.dumps(assessment, ensure_ascii=False, indent=2) + "\n",
    )
    return inspect_authoring_trial(root)


def _average(records: list[dict[str, Any]], field: str) -> float | None:
    values = [record[field] for record in records if record.get(field) is not None]
    return round(mean(values), 2) if values else None


def _approach_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    first_attempt = [
        record["first_attempt_success"]
        for record in records
        if record.get("first_attempt_success") is not None
    ]
    return {
        "sessions": len(records),
        "successful": sum(record.get("outcome") == "success" for record in records),
        "success_rate": (
            round(
                100
                * sum(record.get("outcome") == "success" for record in records)
                / len(records),
                1,
            )
            if records
            else None
        ),
        "first_attempt_measured": len(first_attempt),
        "first_attempt_success_rate": round(
            100 * sum(value is True for value in first_attempt) / len(first_attempt), 1
        ) if first_attempt else None,
        "mean_correction_rounds": _average(records, "correction_rounds"),
        "mean_elapsed_seconds": _average(records, "elapsed_seconds"),
        "input_token_samples": sum(record.get("input_tokens") is not None for record in records),
        "mean_input_tokens": _average(records, "input_tokens"),
        "output_token_samples": sum(record.get("output_tokens") is not None for record in records),
        "mean_output_tokens": _average(records, "output_tokens"),
    }


def _paired_metric(dataviz: dict[str, Any], html: dict[str, Any], field: str) -> dict[str, Any] | None:
    left = dataviz.get(field)
    right = html.get(field)
    if left is None or right is None:
        return None
    delta = left - right
    return {
        "dataviz": left,
        "standalone_html": right,
        "delta_dataviz_minus_html": round(delta, 2),
        "dataviz_reduction_percent": (
            round(100 * (right - left) / right, 1) if right else None
        ),
    }


def build_authoring_evaluation_report(
    sessions: list[dict[str, Any]],
    *,
    task_id: str | None = None,
) -> dict[str, Any]:
    if task_id is not None and task_id not in AUTHORING_TASKS:
        authoring_task_catalog(task_id)
    eligible = [
        record
        for record in sessions
        if record.get("status") == "finished"
        and record.get("benchmark_task")
        and record.get("approach") in AUTHORING_APPROACHES
        and (task_id is None or record.get("benchmark_task") == task_id)
    ]
    groups: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    for record in eligible:
        key = (record["benchmark_task"], record["trial_id"])
        groups.setdefault(key, {}).setdefault(record["approach"], []).append(record)

    diagnostics: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    metric_names = [
        "input_tokens",
        "output_tokens",
        "correction_rounds",
        "elapsed_seconds",
    ]
    for (benchmark_task, trial_id), approaches in sorted(groups.items()):
        duplicate = {
            approach: len(records)
            for approach, records in approaches.items()
            if len(records) != 1
        }
        missing = [
            approach for approach in AUTHORING_APPROACHES if not approaches.get(approach)
        ]
        if duplicate or missing:
            diagnostics.append(
                {
                    "code": "authoring_trial_incomplete",
                    "benchmark_task": benchmark_task,
                    "trial_id": trial_id,
                    "missing": missing,
                    "duplicates": duplicate,
                }
            )
            continue
        dataviz = approaches["dataviz"][0]
        html = approaches["standalone-html"][0]
        identity = {
            "task_match": dataviz.get("task") == html.get("task"),
            "model_match": dataviz.get("model") == html.get("model"),
            "tool_match": dataviz.get("tool") == html.get("tool"),
            "task_contract_match": (
                dataviz.get("task_contract_sha256")
                == html.get("task_contract_sha256")
                and dataviz.get("task_contract_sha256") is not None
            ),
            "fixture_match": (
                dataviz.get("fixture_sha256") == html.get("fixture_sha256")
                and dataviz.get("fixture_sha256") is not None
            ),
        }
        comparable = all(identity.values())
        quality_passed = (
            dataviz.get("outcome") == "success"
            and html.get("outcome") == "success"
            and dataviz.get("trial_integrity_passed") is True
            and html.get("trial_integrity_passed") is True
            and dataviz.get("acceptance_passed") is True
            and html.get("acceptance_passed") is True
        )
        if not comparable:
            diagnostics.append(
                {
                    "code": "authoring_trial_identity_mismatch",
                    "benchmark_task": benchmark_task,
                    "trial_id": trial_id,
                    "matches": identity,
                    "message": (
                        "Paired approaches must use the same task text, model and client/tool"
                        ", fixed task contract and fixture digest"
                    ),
                }
            )
        pairs.append(
            {
                "benchmark_task": benchmark_task,
                "trial_id": trial_id,
                **identity,
                "comparable": comparable,
                "quality_passed": quality_passed,
                "outcomes": {
                    "dataviz": dataviz.get("outcome"),
                    "standalone_html": html.get("outcome"),
                },
                "first_attempt_success": {
                    "dataviz": dataviz.get("first_attempt_success"),
                    "standalone_html": html.get("first_attempt_success"),
                },
                "acceptance_passed": {
                    "dataviz": dataviz.get("acceptance_passed"),
                    "standalone_html": html.get("acceptance_passed"),
                },
                "metrics": {
                    metric: comparison
                    for metric in metric_names
                    if (comparison := _paired_metric(dataviz, html, metric)) is not None
                },
            }
        )

    quality_pairs = [
        pair
        for pair in pairs
        if pair["comparable"] and pair["quality_passed"]
    ]
    aggregate: dict[str, Any] = {}
    for metric in metric_names:
        comparisons = [
            pair["metrics"][metric]
            for pair in quality_pairs
            if metric in pair["metrics"]
        ]
        aggregate[metric] = {
            "paired_samples": len(comparisons),
            "mean_delta_dataviz_minus_html": _average(
                comparisons, "delta_dataviz_minus_html"
            ),
            "mean_dataviz_reduction_percent": _average(
                comparisons, "dataviz_reduction_percent"
            ),
        }

    return {
        "schema": AUTHORING_EVALUATION_SCHEMA,
        "task_filter": task_id,
        "sessions": len(eligible),
        "complete_pairs": len(pairs),
        "comparable_pairs": sum(pair["comparable"] for pair in pairs),
        "quality_pairs": len(quality_pairs),
        "approaches": {
            approach: _approach_metrics(
                [record for record in eligible if record.get("approach") == approach]
            )
            for approach in AUTHORING_APPROACHES
        },
        "paired_trials": pairs,
        "paired_aggregate": aggregate,
        "diagnostics": diagnostics,
        "interpretation": (
            "Paired aggregates include only identity-matched trials where both approaches "
            "preserved the fixed approach prompt and inputs and recorded evidence that every "
            "acceptance check passed. Failed, unassessed or mismatched trials remain visible "
            "but cannot establish an efficiency win. Null token metrics are unmeasured, never "
            "estimated."
        ),
    }
