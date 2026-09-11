import pytest

from dataviz.workspace.models import PresentationControlComponentDefinition


@pytest.mark.parametrize('component', ['select', 'cascader'])
def test_selection_components_accept_shared_action_labels(component):
    spec = PresentationControlComponentDefinition.model_validate({
        'component': component, 'select_all_label': '全选', 'clear_label': '清空',
        'search_placeholder': '搜索',
    })
    assert spec.select_all_label == '全选'
    assert spec.clear_label == '清空'
