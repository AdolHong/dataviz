# SQLite：一个 YAML 完成参数化 SQL 和查询后筛选

从仓库根目录执行；生成器仅创建新文件，已存在则拒绝。下列数据库只含示例数据：

```sh
python examples/local-sqlite/create_data.py /tmp/dataviz-demo-sales.sqlite
dataviz inspect data /tmp/dataviz-demo-sales.sqlite
dataviz inspect data /tmp/dataviz-demo-sales.sqlite --table sales --rows 3
dataviz validate examples/local-sqlite/dashboard.yaml --data warehouse=/tmp/dataviz-demo-sales.sqlite --strict
dataviz serve examples/local-sqlite/ --data warehouse=/tmp/dataviz-demo-sales.sqlite
dataviz report examples/local-sqlite/ --data warehouse=/tmp/dataviz-demo-sales.sqlite --query-param 'minimum={"value":100}' --output /tmp/sales.html
```

打开即分析，修改最低收入后自动更新；品类 Control 直接筛选已有查询结果。最低收入 100 时剩 4 行、合计 515。
昂贵计算可加 `--execution manual`，保留手动 Run；两种模式修改文件都不需要重启。
`warehouse` 绑定整个数据库，SQL 决定使用哪张表，不需要另写 auth 配置。
数据复制为包含已提交 WAL 的快照，SQL 连接只读；原数据库变更后自动模式采用新快照更新当前页。
这里的 `--data` 不是标注写入资源；标注须通过外部 auth 和显式 Server Action 绑定可变数据库。
