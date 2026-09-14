# 多 Page：同一看板，两条分析路径

需要 Dataviz 0.23.0 或本仓库当前源码。无需数据库、Auth、CSV 下载或额外包。
所有数据由 `dashboards/holiday/sales.py` 确定性生成，**完全虚构，不能用于业务判断**。

在 `dataviz-tool` 目录启动：

```bash
dataviz serve examples/multi-page-workspace --host 127.0.0.1 --port 8888
```

源码环境也可以使用 `PYTHONPATH=src .venv/bin/python -m dataviz.cli` 替代 `dataviz`。
打开 http://127.0.0.1:8888/dashboards/holiday，设置参数后点击 **Run**。
若打开根地址且标签页没有历史记录，会先显示空状态，需要在左侧选择看板。

- **同年 · 品类对比**：选择 2023–2026 中的一年，比较水果、烘焙、饮料。
- **同品类 · 跨年对比**：选择一个品类和多个年份，按 T−7～T+7 对齐曲线。
- 两页分别保存参数和运行结果；切到未运行的页后需要自行点击 Run。
- 回到已运行的页可继续查看其结果，切页本身不查询。

## 结构与口径

`workspace.yaml` 只登记 Workspace。`dashboard.yaml` 统一声明两个 Source、两组 Page
参数及原生图表；两个 Source 共用 `sales.py`，没有软链接或跨 Dashboard 依赖。
没有 Section、自定义 Renderer 或共享参数；`trend`、`details` 在两页同名也彼此独立。

数据覆盖 4 年 × 3 品类 × 15 天（最多 180 行日明细）。Python 根据所选页参数生成对应
切片。T=0 为虚构活动日，不使用真实节日日历；跨年按相对日比较。
基线随年份平缓增长，各品类的活动峰值不同。净增量 = 实际销量 − 基线；
增量率 = 净增量 / 基线 × 100，表中的数值已是百分数，不再二次乘 100。

## CLI 验证与执行

```bash
dataviz validate examples/multi-page-workspace --strict
# 默认只运行第一页，不会一起运行两页。
dataviz run examples/multi-page-workspace holiday --format json
dataviz run examples/multi-page-workspace holiday --page history --format json
# 导出第二页刚返回的 result_id，不重查，也不再指定 --page。
dataviz report examples/multi-page-workspace <result-id> --output history.html
```

本例不演示持久化标注。当前工作树支持按 Page 识别热更新，以及共享 Source 保存后的
Data changed 提示；其他页不会自动查询，需要在该页显式 Run。修改共享 Python 后两页
都可能受影响，应重新验证两条路径。旧发行包的能力以对应发行说明为准。

## 验证范围

本例的严格校验、两页执行与图表交互由仓库测试覆盖。推荐桌面浏览器查看，不宣称移动端
完整验收。具体版本的执行结果以对应 `docs/release-*.md` 为准，不能把测试存在当成当前
发行版已经执行通过；工作树改动与已发布安装包也应分开判断。
