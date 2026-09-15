# CSV：一个 YAML 完成取数、Python 汇总和点选联动

从仓库根目录执行（源码环境在命令前加 `PYTHONPATH=src`，用 `.venv/bin/python -m dataviz.cli` 替换 `dataviz`）：

```sh
dataviz inspect data examples/local-csv/sales.csv
dataviz validate examples/local-csv/dashboard.yaml --data sales=examples/local-csv/sales.csv --strict
dataviz serve examples/local-csv/dashboard.yaml --data sales=examples/local-csv/sales.csv
dataviz report examples/local-csv/dashboard.yaml --data sales=examples/local-csv/sales.csv --output /tmp/sales.html
```

打开地址即显示分析；左表点击 food/drink，右侧趋势随选择变化，不重新查数。
修改 CSV、YAML 或声明的代码文件后自动更新，不需要重启。昂贵计算可加 `--execution manual`。
可选 `--refresh-interval 10`：每次完成后等待 10 秒再重新计算，慢任务不积压；默认不开定时器。
也可将 YAML 参数换成 `examples/local-csv/`，无需 workspace.yaml。
换自己的 CSV 时保留 date/category/revenue 列，并调整 YAML 的品类选项。
代码变长后可将 `code.inline` 拆成同目录 `.py` 文件，仍是独立 Dashboard。

`run` 同样接受 `--data` 并返回 Result 与后续命令；导出旧结果使用返回的原快照路径，
不要拿修改后的数据重新构造旧 Result。示例总收入 food=405、drink=285。
