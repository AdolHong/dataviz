# 0.25.7 本地发行验收

日期：2026-09-14。JSON/Arrow 浏览器数据一致性修复，不改 DSL。
具体值契约、兼容注意事项和原始失败记录见 [输入输出一致性审计](io-contract-audit.md)。
日期改为 ISO 字符串，大整数和 Decimal 使用精确字符串；Python Artifact 不变。

## 复用的源码验证

- 非浏览器全套 807 passed：`.test-evidence/io-nonbrowser-complete.log`。
- 三浏览器核心各 16 passed：`.test-evidence/io-boundary-core-complete.log`。
- 三浏览器真实单元格、columnar、快照各 1 passed：`.test-evidence/io-rich-cells.log`。
- 三浏览器 Server/Share/HTML 强制 JSON/Arrow 各 2 passed：`.test-evidence/io-three-surfaces-final.log`。
- 三浏览器 JSON/Arrow/auto 与缓存各 5 passed：`.test-evidence/io-worker-cache-final.log`。
- 早期 Firefox 停滞根因尚未确定，已保留证据；后续通过不代表修复该停滞。

本次仅升版及打包，复用上述产品代码的测试，不重跑完整浏览器矩阵。
构建检查记录于 `.test-evidence/release0257-build.log` 与 `.test-evidence/release0257-checks.log`。
wheel 配套 Skill 保持同源打包。本地构建不代表远端 CI、多 Python 版本验证或 PyPI 上传。
