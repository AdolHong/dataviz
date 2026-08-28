# Feature Showcase

五个当前 v2 看板组成的功能验收 Workspace，覆盖多数据入口、Query/Selection、相对日期与 Range Picker、级联组件、图表、Table/Perspective、Dataset Transform、Interactive Transform 与自定义 Presentation。

`date-parameter-lab` 演示了两种相对默认值：单日期的“今天 -1 天”，以及 Range Picker 的“今天 -7 天到今天 -1 天”。在 Server 中右键 `RUN`，展开对应参数即可编辑默认偏移天数。

所有 SQL Source 都只引用逻辑 Adapter `warehouse`，真实绑定集中在各看板的 `dashboard.yaml`。把看板文件夹发给同事后，只需把：

```yaml
adapters:
  warehouse: demo-duckdb
```

改成同事 Workspace 中的 Adapter 名，例如 `team-starrocks`。非敏感定义放在 `auth/adapters.yaml`，账号密码只放在 `auth/adapters.local.yaml` 或环境变量中。
