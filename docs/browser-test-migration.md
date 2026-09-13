# 浏览器测试迁移记录

本页记录首次分层；后续深度精简见 [browser-test-pruning.md](browser-test-pruning.md)。
以下“原样迁移”指首次拆分时的状态，不代表后续从未修改。

首次机械拆分：84 个测试函数的 AST（含装饰器）逐一相等。后续下沉／合并另列替代覆盖，不默默删断言。

## 合并与替代覆盖

- `analysis_stability_workflow`：去掉未使用的 `round_index` 三次参数化，同一数据和操作只运行一次；用例内部往返选择与分析断言保留。
- `table_row_count_is_opt_in_instead_of_a_default_metadata_row`：保留 server/share/html 三种形态的元信息、真实 TanStack API、初始分页集成检查。排序、中文输入法、搜索、分页、焦点和横向滚动下沉到 `components/test_table.py` 的五个独立测试，不再在三种形态重复整段交互。
- `components/test_choices.py`：真实组件资产上的搜索结果全选／清空、键盘与窄屏行高检查；完整看板中的级联及导出集成回归仍保留。
- `components/test_inputs.py`：同步时保留草稿和光标；完整看板的其他控件提交确认链路仍由原集成回归覆盖，两者并非相同契约。

首次分层收集数量：原完整集合 120 项，合并重复轮次后 118 项，新增 12 项组件用例后 130 项。后续精简级联矩阵并增加独立 checkbox 回归后为 125 项（核心 16、组件 13）。固定 Chromium 的 9 项 CLI 契约不再在 Firefox/WebKit 分组重复执行，其两组各收集 116 项。

本次验证：三浏览器组件层各 12 项通过（约 4～9 秒），核心层各 16 项通过（约 4 分钟）。扩展全集未重跑；机械迁移检查不等于重新执行全部扩展测试。

定向扩展验证：表格三种形态及失败证据自测共 5 项，三浏览器各通过（约 22～29 秒）；新增光标位置断言另行三浏览器通过。测试入口、迁移与质量配置相关非浏览器测试 17 项通过。
日志分别保存在 `.test-evidence/test-layers-components/`、`test-layers-core/`、`test-layers-table/` 和 `test-layers-input-caret/`（后面三者也位于 `.test-evidence/`）。

| 原测试函数 | 当前位置 | 覆盖处理 |
| --- | --- | --- |
| `test_three_surface_shell_audit` | `tests/e2e/extended/test_shell.py` | 原样迁移，断言不变 |
| `test_three_surface_choice_and_date_controls` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_root_requires_explicit_or_remembered_dashboard` | `tests/e2e/core/test_navigation.py` | 原样迁移，断言不变 |
| `test_cascader_search_density_and_exported_sidebar_corners` | `tests/e2e/extended/test_cascader.py` | 原样迁移，断言不变 |
| `test_cascader_sidebar_bounds_and_global_all` | `tests/e2e/extended/test_cascader.py` | 原样迁移，断言不变 |
| `test_contextual_controls_sidebar_and_portable_state` | `tests/e2e/extended/test_shell.py` | 原样迁移，断言不变 |
| `test_contextual_controls_sibling_switch_and_popover_override` | `tests/e2e/extended/test_shell.py` | 原样迁移，断言不变 |
| `test_pages_preserve_independent_queries_and_history` | `tests/e2e/core/test_navigation.py` | 原样迁移，断言不变 |
| `test_multi_page_example_renders_both_analysis_paths` | `tests/e2e/extended/test_navigation.py` | 原样迁移，断言不变 |
| `test_shared_action_marks_sibling_page_without_querying` | `tests/e2e/core/test_actions_and_analysis.py` | 原样迁移，断言不变 |
| `test_analysis_stability_workflow` | `tests/e2e/core/test_actions_and_analysis.py` | 合并三次相同轮次，内部断言保留 |
| `test_server_only_large_input_stays_out_of_browser` | `tests/e2e/extended/test_large_data.py` | 原样迁移，断言不变 |
| `test_custom_selection_feedback_updates_without_data_change` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_standalone_inline_python_renders_without_sidebar` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_server_action_updates_canvas_in_place_and_preserves_query_draft` | `tests/e2e/core/test_actions_and_analysis.py` | 原样迁移，断言不变 |
| `test_query_multiple_select_summary_prefers_the_human_scale` | `tests/e2e/extended/test_large_data.py` | 原样迁移，断言不变 |
| `test_parameter_lookup_does_not_reconcile_a_new_selection_with_old_operands` | `tests/e2e/extended/test_parameter_domains.py` | 原样迁移，断言不变 |
| `test_parameter_domain_cascade_reload_and_tab_restore` | `tests/e2e/extended/test_parameter_domains.py` | 原样迁移，断言不变 |
| `test_server_compute_waits_for_required_control_domain` | `tests/e2e/core/test_controls.py` | 原样迁移，断言不变 |
| `test_operation_panel_shortcuts_and_responsive_state` | `tests/e2e/core/test_shell.py` | 原样迁移，断言不变 |
| `test_navigation_supersedes_slow_page_and_lookup_requests` | `tests/e2e/core/test_queries.py` | 原样迁移，断言不变 |
| `test_parameter_domain_lookup_search_and_cursor_pagination` | `tests/e2e/extended/test_parameter_domains.py` | 原样迁移，断言不变 |
| `test_remote_single_select_search_repaints_with_scalar_state` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_remote_lookup_late_failure_cannot_replace_newer_success` | `tests/e2e/extended/test_parameter_domains.py` | 原样迁移，断言不变 |
| `test_parameter_domain_failure_does_not_trap_dashboard_navigation` | `tests/e2e/extended/test_parameter_domains.py` | 原样迁移，断言不变 |
| `test_sidebar_updates_dashboard_url_before_dynamic_domain_hydration` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_parameter_domain_generation_is_scoped_per_dashboard` | `tests/e2e/extended/test_parameter_domains.py` | 原样迁移，断言不变 |
| `test_hard_expired_parameter_domain_disables_only_its_pickers` | `tests/e2e/extended/test_parameter_domains.py` | 原样迁移，断言不变 |
| `test_date_parameter_inputs_share_iso_text_and_calendar_contract` | `tests/e2e/extended/test_query_authoring.py` | 原样迁移，断言不变 |
| `test_header_overlays_stay_in_viewport_and_query_parameters_are_discoverable` | `tests/e2e/extended/test_query_authoring.py` | 原样迁移，断言不变 |
| `test_portable_query_tray_uses_shared_sidebar_for_clicks_and_shortcuts` | `tests/e2e/core/test_queries.py` | 原样迁移，断言不变 |
| `test_workspace_hot_reload_preserves_run_and_marks_query_contract_outdated` | `tests/e2e/extended/test_query_authoring.py` | 原样迁移，断言不变 |
| `test_committed_parameter_content_and_stale_selection_export` | `tests/e2e/extended/test_query_authoring.py` | 原样迁移，断言不变 |
| `test_canvas_messages_are_bound_to_the_current_frame_instance` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_control_runtime_channel_is_versioned_idempotent_and_checkpointed` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_view_applied_state_advances_only_for_current_ready_generation` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_section_selection_updates_bound_title_without_redrawing_siblings` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_sources_inspector_exposes_resolved_and_parameterized_sql` | `tests/e2e/extended/test_query_authoring.py` | 原样迁移，断言不变 |
| `test_selection_impact_count_resolves_against_loaded_output_schemas` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_sources_inspector_loads_structured_python_execution_log` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_web_component_reference_adapter_consumes_runtime_v2_without_canvas_runtime` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_multiple_input_keeps_blank_draft_during_other_control_commit` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_component_gallery_story_overlay_keyboard_a11y_and_virtual_dom` | `tests/e2e/extended/test_component_gallery.py` | 原样迁移，断言不变 |
| `test_sidebar_query_grid_keeps_bounded_fields_and_equal_entry_heights` | `tests/e2e/extended/test_query_authoring.py` | 原样迁移，断言不变 |
| `test_query_control_tray_is_responsive_bounded_and_selector_safe` | `tests/e2e/extended/test_query_authoring.py` | 原样迁移，断言不变 |
| `test_cross_browser_narrow_control_overlay_keyboard_scroll_and_aria` | `tests/e2e/extended/test_control_layout.py` | 原样迁移，断言不变 |
| `test_server_header_hydrates_dataset_driven_dashboard_selection_options` | `tests/e2e/extended/test_shell.py` | 原样迁移，断言不变 |
| `test_unified_dashboard_controls_drive_browser_named_output` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_sidebar_dashboard_can_be_dragged_and_renamed_from_context_menu` | `tests/e2e/extended/test_navigation.py` | 原样迁移，断言不变 |
| `test_selection_cascade_popovers_view_isolation_and_table_wheel` | `tests/e2e/extended/test_cascader.py` | 原样迁移，断言不变 |
| `test_managed_renderer_lifecycle_matrix_in_server_and_export` | `tests/e2e/extended/test_renderers.py` | 原样迁移，断言不变 |
| `test_three_surface_renderer_pending_error_and_recovery` | `tests/e2e/extended/test_renderers.py` | 原样迁移，断言不变 |
| `test_perspective_async_mount_has_bounded_table_fallback` | `tests/e2e/extended/test_perspective.py` | 原样迁移，断言不变 |
| `test_same_view_control_dependency_reconciles_in_server_and_export` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_plotly_defaults_to_page_wheel_and_allows_explicit_scroll_zoom` | `tests/e2e/extended/test_plotly_binding.py` | 原样迁移，断言不变 |
| `test_perspective_fills_view_uses_opaque_settings_and_releases_page_wheel` | `tests/e2e/extended/test_perspective.py` | 原样迁移，断言不变 |
| `test_perspective_enters_empty_state_immediately_after_last_selection_is_cleared` | `tests/e2e/extended/test_perspective.py` | 原样迁移，断言不变 |
| `test_cross_browser_perspective_repeated_dispose_and_restore` | `tests/e2e/extended/test_perspective.py` | 原样迁移，断言不变 |
| `test_required_dynamic_view_selection_bootstraps_from_base_output_and_exports` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_parameter_editor_choice_rows_share_the_drag_sorting_model` | `tests/e2e/extended/test_query_authoring.py` | 原样迁移，断言不变 |
| `test_date_default_editor_uses_one_mode_and_one_value_per_endpoint` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_query_reload_restores_visible_date_range_and_single_select` | `tests/e2e/core/test_queries.py` | 原样迁移，断言不变 |
| `test_browser_query_inputs_project_date_range_parts` | `tests/e2e/extended/test_query_authoring.py` | 原样迁移，断言不变 |
| `test_share_link_keeps_browser_interactions_and_uses_workspace_cache` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_browser_transform_session_cache_reuses_equivalent_control_state` | `tests/e2e/extended/test_execution.py` | 原样迁移，断言不变 |
| `test_browser_js_interactive_worker_cancellation_timeout_and_serializable_error` | `tests/e2e/extended/test_execution.py` | 原样迁移，断言不变 |
| `test_server_python_and_browser_js_share_output_contract_and_block_html_export` | `tests/e2e/extended/test_execution.py` | 原样迁移，断言不变 |
| `test_selection_gallery_canonical_empty_all_and_clear` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_native_table_distinguishes_all_available_from_explicit_empty` | `tests/e2e/extended/test_control_state.py` | 原样迁移，断言不变 |
| `test_plotly_control_binding_commits_once_and_keeps_bound_candidates` | `tests/e2e/extended/test_plotly_binding.py` | 原样迁移，断言不变 |
| `test_queued_plotly_writer_actions_survive_source_view_rerender` | `tests/e2e/extended/test_plotly_binding.py` | 原样迁移，断言不变 |
| `test_plotly_writer_real_mouse_gestures_commit_at_human_cadence` | `tests/e2e/extended/test_plotly_gestures.py` | 原样迁移，断言不变 |
| `test_plotly_writer_recovers_wrong_or_missing_raw_click` | `tests/e2e/extended/test_plotly_gestures.py` | 原样迁移，断言不变 |
| `test_plotly_native_double_click_restores_zoom_without_resetting_control` | `tests/e2e/extended/test_plotly_gestures.py` | 原样迁移，断言不变 |
| `test_multi_view_linked_brushing_preserves_writer_provenance_across_runtime` | `tests/e2e/extended/test_plotly_binding.py` | 原样迁移，断言不变 |
| `test_plotly_area_selection_gesture_commits_the_bound_control` | `tests/e2e/extended/test_plotly_gestures.py` | 原样迁移，断言不变 |
| `test_table_row_count_is_opt_in_instead_of_a_default_metadata_row` | `tests/e2e/extended/test_control_state.py` | 保留三形态集成，局部交互下沉至五个组件测试 |
| `test_table_control_binding_writes_the_shared_selection` | `tests/e2e/core/test_controls.py` | 原样迁移，断言不变 |
| `test_arrow_transport_and_repeat_thousand_group_search_lazy_budget` | `tests/e2e/extended/test_large_data.py` | 原样迁移，断言不变 |
| `test_progressive_failure_and_consecutive_run_are_isolated` | `tests/e2e/extended/test_execution.py` | 原样迁移，断言不变 |
| `test_large_aggregations_do_not_cross_the_javascript_argument_limit` | `tests/e2e/extended/test_large_data.py` | 原样迁移，断言不变 |
| `test_cancelled_query_branch_reaches_a_terminal_view_state` | `tests/e2e/extended/test_query_authoring.py` | 原样迁移，断言不变 |
| `test_workspace_asset_service_matches_server_and_portable_html` | `tests/e2e/extended/test_renderers.py` | 原样迁移，断言不变 |
| `test_native_map_point_region_asset_and_selection_match_server_and_portable` | `tests/e2e/extended/test_renderers.py` | 原样迁移，断言不变 |
