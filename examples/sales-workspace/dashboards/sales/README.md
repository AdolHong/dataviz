# 销售脉搏

这是一个自包含示例。一行订单代表某天、某区域的一组销售记录。收入单位为人民币元。

`target_factor` 是取数参数，用于模拟 SQL 目标调整。

`region` 是 Dashboard Selection；`min_revenue` 是经营脉搏 Section Selection；`min_orders` 只属于明细 View。Server 和导出 HTML 都在浏览器中把三者应用到已加载的数据集，不会重新查询数据源。
