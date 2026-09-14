from __future__ import annotations

import json
import re
import shlex

import pytest
from typer.testing import CliRunner

from dataviz.cli import app
import dataviz.documentation as documentation


@pytest.mark.parametrize('query,required', [
    ('保存未确认', ['actions status', '不要自动换 ID', '业务事务已经回滚']),
    ('保存成功但刷新失败', ['actions refresh', '不重复执行写入']),
    ('action_not_submitted', ['未提交', '不要批量盲重试']),
    ('查询一直 Loading', ['Retry status', '不重复提交查询']),
])
def test_recovery_symptoms_route_to_safe_troubleshooting(query, required):
    match = next(item for item in documentation.search_documentation(query)['results']
                 if item['topic'] == 'troubleshooting')
    response = CliRunner().invoke(app, shlex.split(match['command'])[1:])
    assert response.exit_code == 0, response.output
    for phrase in required:
        assert phrase in response.stdout
    # Follow the related public topics rather than silently publishing a typo.
    for topic in set(re.findall(r'docs ([a-z][a-z-]+)', response.stdout)):
        linked = CliRunner().invoke(app, ['docs', topic, '--format', 'json'])
        assert linked.exit_code == 0, linked.output


def test_control_docs_match_scoped_bulk_actions_without_menu_revert():
    response = CliRunner().invoke(app, ["docs", "controls", "--format", "json"])
    assert response.exit_code == 0, response.output
    document = json.loads(response.stdout)
    text = json.dumps(document, ensure_ascii=False)
    for phrase in ('Select results / Clear results', '保留搜索外选择',
                   '未加载的分页', '菜单没有 Revert', 'committed Query snapshot'):
        assert phrase in text
    for stale in ('本次打开期间的 Revert', '多选提供 Select all / Clear / Revert',
                  '不受搜索过滤影响'):
        assert stale not in text


def test_query_reload_diagnosis_is_discoverable_by_symptom():
    result = next(item for item in documentation.search_documentation("刷新 默认值")["results"]
                  if item["topic"] == "query-parameters")
    response = CliRunner().invoke(app, shlex.split(result["command"])[1:])
    assert response.exit_code == 0, response.output
    assert "reload_restoration" in response.stdout
    assert "可见组件必须一起同步" in response.stdout


def test_view_diagnosis_privacy_and_unknown_state_are_documented():
    response = CliRunner().invoke(app, ["docs", "interaction-stability", "--format", "json"])
    assert response.exit_code == 0
    assert "Copy diagnosis" in response.stdout
    assert "unknown" in response.stdout
    assert "分享前需审阅" in response.stdout
    assert "GET 最多等待 30 秒" in response.stdout
    assert "不取消服务端 Query" in response.stdout


def test_view_triage_can_be_found_without_runtime_implementation_names():
    matches = documentation.search_documentation('图表没刷新')["results"]
    match = next(item for item in matches if item['topic']=='interaction-stability')
    response = CliRunner().invoke(app, shlex.split(match['command'])[1:])
    assert response.exit_code == 0
    for phrase in ['input_type', 'pending', 'control_state', 'not_affected', 'cache=hit', 'output_fetch_failed']:
        assert phrase in response.stdout


@pytest.mark.parametrize("query", ["级联候选为空", "右图漏刷"])
def test_interaction_stability_is_discoverable_by_symptom(query):
    match = next(item for item in documentation.search_documentation(query)["results"]
                 if item["topic"] == "interaction-stability")
    response = CliRunner().invoke(app, shlex.split(match["command"])[1:])
    assert response.exit_code == 0, response.output
    assert "controlDomainEvidence" in response.stdout
    assert "field_mismatch" in response.stdout


@pytest.mark.parametrize("query", ["高亮不更新", "controlBinding state"])
def test_renderer_selection_feedback_is_discoverable(query):
    results = documentation.search_documentation(query)["results"]
    match = next(item for item in results if item["topic"] == "renderer-selection")
    response = CliRunner().invoke(app, shlex.split(match["command"])[1:])
    assert response.exit_code == 0, response.output
    assert "state.context" in response.stdout
    assert "binding_revisions" in response.stdout


def test_task_search_result_opens_the_document_containing_the_match():
    payload = documentation.search_documentation("post-query child")
    result = next(item for item in payload["results"] if item["topic"] == "task:cascading-selection")
    response = CliRunner().invoke(app, shlex.split(result["command"])[1:])
    assert response.exit_code == 0, response.stdout
    document = json.loads(response.stdout)["documents"]["cascading-selection"]
    assert result["snippet"] == document[result["path"]]


def test_topic_alias_search_returns_a_working_topic_command():
    payload = documentation.search_documentation("input-component")
    assert payload["results"][0]["topic"] == "data-entry-components"
    response = CliRunner().invoke(app, shlex.split(payload["results"][0]["command"])[1:])
    assert response.exit_code == 0
    assert json.loads(response.stdout)["topic"] == "data-entry-components"


def test_complete_matches_precede_partial_fallback_and_limits_stay_bounded(monkeypatch):
    monkeypatch.setattr(documentation, "DOC_TOPICS", {
        "example": {"summary": "alpha beta", "detail": "alpha only", "extra": "beta alpha"},
    })
    monkeypatch.setattr(documentation, "AUTHORING_DOCUMENTS", {})
    complete = documentation.search_documentation("alpha beta", limit=1)
    assert complete["returned"] == 1
    assert complete["total"] == 2
    assert complete["truncated"]
    assert "alpha" in complete["results"][0]["snippet"]
    assert "beta" in complete["results"][0]["snippet"]
    fallback = documentation.search_documentation("alpha missing")
    assert fallback["total"] == 3
    assert documentation.search_documentation("unknownterm")["results"] == []


@pytest.mark.parametrize("limit", [0, -1])
def test_search_rejects_nonpositive_limits(limit):
    with pytest.raises(ValueError, match="positive"):
        documentation.search_documentation("select", limit=limit)


def test_blank_search_is_an_actionable_cli_error():
    response = CliRunner().invoke(app, ["docs", "--search", "   "])
    assert response.exit_code != 0
    assert "non-empty query" in response.output


def test_repeated_terms_do_not_inflate_match_counts():
    single = documentation.search_documentation("Control initial")
    repeated = documentation.search_documentation("Control initial initial")
    assert repeated["total"] == single["total"]
    assert {item["topic"] for item in repeated["results"]} == {
        item["topic"] for item in single["results"]
    }


def test_server_action_discovery_exposes_context_and_write_boundaries():
    results = documentation.search_documentation("writeback")["results"]
    match = next(item for item in results if item["topic"] == "server-actions")
    response = CliRunner().invoke(app, shlex.split(match["command"])[1:])
    assert response.exit_code == 0, response.output
    document = json.loads(response.stdout)
    assert document["topic"] == "server-actions"
    # Search must open the real contract, not an unimplemented command suggestion.
    assert "resources.config(alias)" in response.stdout
    assert "context.actions.refresh(action, requestId)" in response.stdout
    assert "unknown" in response.stdout


def test_server_action_schema_is_discoverable_and_strict():
    response = CliRunner().invoke(app, [
        "schemas", "server-action", "--full", "--format", "json",
    ])
    assert response.exit_code == 0, response.output
    assert "dataviz/server-action/v1" in response.stdout
    assert "invalidates" in response.stdout
    from dataviz.actions import ServerActionDefinition
    schema = ServerActionDefinition.model_json_schema(by_alias=True)
    assert schema["additionalProperties"] is False
    assert {"schema", "id", "code"} <= set(schema["required"])


@pytest.mark.parametrize("query", ["保存慢", "人工标注", "checkbox 保存 SQLite", "保存后局部刷新"])
def test_save_scenarios_find_runnable_recipe_first(query):
    first = documentation.search_documentation(query)["results"][0]
    assert first["topic"] == "action-save"
    response = CliRunner().invoke(app, shlex.split(first["command"])[1:])
    assert response.exit_code == 0, response.output
    content = json.loads(response.stdout)
    assert content["recipe"]["annotation.yaml"]["server_actions"][0]["id"] == "save_label"
    assert "onProgress(receipt)" in content["progress_contract"]
