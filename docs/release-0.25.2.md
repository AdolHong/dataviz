# 0.25.2 本地补丁构建

本次包含浏览器测试分层、执行成本优化，以及复选框同步吞点击修复；不改变 DSL。
Skill 继续由 `dataviz-skill.md` 随 wheel 打包到
`dataviz/skills/dataviz/SKILL.md`，没有新增作者操作需要改写 Skill。

## 复用与补充验证

- 修复前完整非浏览器：785 passed，125 deselected，1 条 Starlette/httpx 依赖弃用 warning；
  证据 `.test-evidence/user-full-20260913-nonbrowser.log`。
- 修复前完整浏览器：Chromium 125 passed、WebKit 116 passed；Firefox 115 passed / 1 failed。
  证据 `.test-evidence/user-full-20260913-browsers/`，保留首次失败，不将重试变绿视为修复。
- Firefox 失败定位到复选按钮在操作途中被同步重建；确定性鼠标、键盘复现修复前均失败。
  修复后组件层三浏览器各 15 passed；新增动态选项约束测试后复选框定向各 4 passed；
  原失败级联 E2E 三浏览器各 1 passed。相关非浏览器 runtime/declarative/authoring 156 passed。
  详细证据见 [checkbox-sync-regression.md](checkbox-sync-regression.md)。
- 此次打包只补版本、构建与包内容核验，不重新跑完整浏览器矩阵。
  既有结果用于未受影响范围；不宣称最新源码完整矩阵或远端 CI 已通过。

这是本地发行产物，不代表 PyPI 上传、Git 发布或远端多 Python 环境门禁完成。
