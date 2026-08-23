# DSL 版本与发布流程

## 四类版本

- Python package：`workspace-dataviz 0.x`。
- 文件 DSL：`dataviz/workspace/v1`、`dashboard/v1`、`source/v1` 等。
- 浏览器协议：`dataviz/runtime/v1`。
- Component Registry：当前 `3.x`（具体版本由 `dataviz version` 输出）。

它们不会因为 package 发补丁版本而被隐式同步升级。`dataviz version` 是安装环境的权威版本清单；`dataviz schemas` 从当前 Pydantic 模型生成字段文档。

## 修改 DSL

1. 为新契约定义新的 Schema URI 和严格 Pydantic 模型。
2. 在 `dataviz.migrations` 注册旧 URI 到新 URI 的确定性离线函数。
3. 为 before/after、幂等、未知版本 blocker 和真实 Workspace 添加测试。
4. 更新 Changelog 与 Scaffold；先让用户运行 `dataviz migrate WORKSPACE` 预览，再显式 `--apply`。
5. Runtime 只读取迁移后的新文件。不得添加“旧字段或新字段都接受”的双协议分支。

当前 v1 没有历史语义版本。迁移器能安全地为可无歧义判断类型的 standalone definition 补 `schema`，未知 v0/v2 则阻断，直到项目明确注册迁移。

## 发布验证

CI 分为三层：

1. Python 3.11、3.12、3.13、3.14 运行 unit/contract tests；macOS 3.12 再验证本项目遇到过的非 editable 安装路径。
2. Chromium、Firefox、WebKit 分别运行真实页面测试，包括 Overlay、Selection、Worker、Repeat 与第二 Web Component Adapter。
3. 同一次构建生成 wheel、sdist 和 pip-installable ZIP；三者分别装进干净 venv，执行 `version`、`schemas`、`components --check`、`init`、`validate` 和 `report`。

```bash
uv build
python scripts/build_release_zip.py
```

ZIP 使用固定时间戳和排序，连续构建内容可复现，并生成 `.zip.sha256`。发行物不得包含 `.venv`、`build/`、缓存、凭证或 Workspace `.dataviz` Runtime 数据。
