# DSL 版本与发布流程

## 独立版本

Dataviz 分别维护 Python package、文件 DSL、Compiler Contract、状态快照、Browser Runtime、Analysis Result/Evidence、Server 事件和 Component Registry 的版本。它们不会因为 package 发布补丁版本而机械同步升级。

安装环境的当前权威清单来自：

```bash
dataviz version
dataviz schemas --format json
dataviz components list --format json
```

## 修改公开契约

项目仍处于未投入生产的 `0.x` 阶段，采用严格断代：

1. 为新语义定义新的 Schema URI 或协议版本。
2. 更新严格 Pydantic 模型、Loader、Runtime Manifest 和事件。
3. 同一次变更改写仓库中的示例、fixture、Snapshot、CLI docs 和测试。
4. 删除被替代的模型、字段、命令和执行分支。
5. 在 Changelog 中提供人工改写说明。

不添加旧字段 alias、deprecated 双写、自动迁移器或双协议 Runtime。旧文件会被当前 Loader 明确拒绝，使用者必须先按新契约改写。

Component Registry 只在公开组件契约变化时升级；单个 Package 可以拥有自己的版本，不跟随 Dashboard DSL 改号。

## 发布前验证

最低门禁：

1. Python 3.11、3.12、3.13、3.14 运行 unit/contract tests。
2. CI distribution job 依赖 Chromium、Firefox、WebKit 三浏览器矩阵全部通过，覆盖 Query/Interaction isolation、两种 Interactive Runtime、Overlay、Control binding、Renderer 和 HTML Export。本地迭代按 AGENTS.md 选择相关测试；公共 Runtime 改动扩大到三浏览器核心，不因为升版或单项失败机械重跑全套。本地定向验收不能替代 CI 发布门禁，也不能表述为完整矩阵通过。
3. `dataviz components check` 的 Package 元数据/资产/测试声明检查通过；组件行为由前两项 pytest 与浏览器 E2E 执行。
4. 四个代表性 Workspace 通过 `validate`，并至少执行一个 Query/Report smoke。
5. wheel、sdist 和 pip-installable ZIP 分别进入干净 venv，运行 `version`、`schemas`、`components check`、`init`、`validate` 和 `report`。
6. 文档只描述当前代码；计划能力必须留在 `plan.md`。

构建：

```bash
uv build
python scripts/build_release_zip.py
# 或先写入临时目录做本地验收
python scripts/build_release_zip.py --output-dir /tmp/dataviz-release
```

维护源码时继续显式使用 `PYTHONPATH=src`。`.venv/bin/python scripts/check_version_drift.py` 只比较项目声明、源码版本与当前 Python 实际导入的版本/路径，明确暴露旧安装，但不包装 CLI、测试、构建或发布。需要刷新普通安装命令时使用 `uv sync --extra dev --no-editable --reinstall-package ai-dataviz`。发行门禁仍按上面的独立步骤执行，不能把源码测试混作发行包证据。

建议把产物写入临时目录先做安装 smoke，确认后再生成正式 `dist/`。

发行 ZIP 使用固定时间戳和排序，完整构建并校验 CRC/文件清单后，才以可回滚事务发布 ZIP 与 `.zip.sha256`。wheel、sdist 和 ZIP 不得包含：

- `.venv/`
- `build/`
- `__pycache__/`、pytest/工具缓存
- Workspace `.dataviz/` Run/Cache
- `auth/adapters.local.yaml`、环境变量或其他凭证

## 版本号

- patch：当前公开契约不变的修复、文档或内部优化。
- minor：`0.x` 阶段新增能力，或明确的 Breaking DSL/Runtime 断代。
- major：进入稳定生产承诺后再定义。

每次发布同时更新 `pyproject.toml`、`src/dataviz/__init__.py`（若版本在此声明）、README 安装示例和 CHANGELOG；运行 `uv lock` 同步项目自身版本，检查 diff 不应顺带升级无关依赖，再运行 `uv lock --check`。用 `dataviz version` 核对最终 wheel，而不是只检查源码文本。
