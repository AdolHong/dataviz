# 0.25.6 本地发行验收

日期：2026-09-14。恢复 Server Parameters 按钮右键编辑当前页默认配置；
保留 Run 右键入口，编辑器加载失败显示提示。不改 DSL、布局或 Share/HTML 只读边界。

## 相关验证

- 修复前 Chromium 新增回归复现编辑器不打开：`.test-evidence/parameter-context-before.log`。
- 修复后非浏览器编辑器契约 5 passed：`.test-evidence/parameter-context-contracts.log`。
- 三浏览器扩展定向各 2 passed：Parameters 右键在侧栏打开/关闭时均可用、保存默认值、
  Run 旧入口、Controls 编辑及不触发查询。`.test-evidence/parameter-context-after.log`。
- 三浏览器核心定向各 3 passed：多 Page 编辑隔离和侧栏快捷键。
  `.test-evidence/parameter-context-core.log`。
- 本次升版复用上述同一产品代码的三浏览器结果，只追加参数编辑器与发行检查，
  记录于 `.test-evidence/release0256-checks.log`。没有重新运行全量。

wheel 配套 Skill 保持同源打包；本地构建不代表远端 CI、多 Python 版本验证或 PyPI 上传。
