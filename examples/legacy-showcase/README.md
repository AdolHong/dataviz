# Legacy Showcase

从 `dashboard2/data/files` 中四个 2025 年旧看板迁移而来。第五个 `demo_ruleengine` 依赖旧系统私有的 ruleflow 运行时，不属于这四个通用数据看板。

所有 SQL Source 都只引用逻辑 Adapter `warehouse`，真实绑定集中在各看板的 `dashboard.yaml`。把看板文件夹发给同事后，只需把：

```yaml
adapters:
  warehouse: demo-duckdb
```

改成同事 Workspace 中的 Adapter 名，例如 `team-starrocks`。账号密码只放在 Workspace 的 `auth/adapters.local.yaml` 或环境变量中。
