# 0.25.3 本地补丁构建

包含异步时序与生命周期专项：单选控件同步保留操作、Renderer 迟到结果隔离与清理、
Transform 销毁后的执行/发布保护，以及 Server Action 等待宿主确认当前 Run。
不改变 DSL 或视觉设计。CLI 文档与配套 Skill 已同步生命周期边界，Skill 继续随 wheel
发布到 `dataviz/skills/dataviz/SKILL.md`。

## 复用验证

- 相关非浏览器最终分组 158 passed，另有 bootstrap 相关 91 passed、文档与 Skill 20 passed；
  分组存在重叠，不相加作为独立用例数。
- 组件层三浏览器各 33 passed；随后新增 bootstrap 回归，受影响 Renderer 分组三浏览器各
  14 passed，其余未变用例复用前轮结果。当前组件层共 34 项。
- 核心层 Chromium、Firefox 各 16 passed；WebKit 首轮 15 passed / 1 failed，定位到 Action
  在宿主确认 Run 前提交。保留首次失败并修复，相关 Action 分组三浏览器各 3 passed。
- Renderer Server/HTML 与 lookup 定向场景三浏览器通过。首次失败和各轮精确范围见
  [异步专项记录](async-lifecycle-workstream.md)。
- 本轮仅升版、构建和包核验，不重新执行完整测试矩阵；既有结果只覆盖未再改变的相关代码。

这是本地发行产物，不代表完整矩阵重新通过、多 Python 环境门禁完成、PyPI 上传或远端 CI 发布。
