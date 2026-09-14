# 0.25.8 本地发行验收

本次发布升级验收、失败传播和诊断改进，不新增 DSL。
具体范围与限制见 [专项验收](stability-upgrade-acceptance.md)。

复用上一轮源码验证：非浏览器阶段 816 passed；最终定向回归 24 passed；
真实 0.25.6 升级对照 4 passed；最终 Chromium/Firefox/WebKit 核心各 16 passed。
历史 Firefox 停滞根因仍未确定，不能把监护与诊断改进称为已修复应用停滞。

此次仅升版、构建并核验配套 Skill 和安装包，不重跑完整测试矩阵。
构建与检查日志：`.test-evidence/release0258-build.log`、
`.test-evidence/release0258-checks.log`。
仅本地打包，不代表远端 CI 通过或上传 PyPI。
