# 打包代码

```shell

tar -czvf ../dataviz_$(date +%Y%m%d_%H%M%S).tar.gz  --exclude backend/engine_config.py backend

```

# 启动前端, 并将处理不了的请求导向 index.html

npm install http-server -g
http-server -P "http://localhost:8080/?"

# python 启动

uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# react 启动

npm start

# react 编译

npm run build
npx tsc

```



20. viz提供playground，可以复制当前queryStaus和代码，进行画图
21. share就很有意思…再想想; share如果有个share管理就好了； 离职也能带走一些东西
33. report的json导出， json导入;
34. 文件拖拽方式的json导入

38. 复制文件功能是 假复制....(😂哭死)

45. 还没query时，  我也想看parsed_code
53. cascader和inferredColumn，弄成全局的；  并且可以设置局部不受影响；
54. toggle 文件夹时， artifact没有autosize。。😂
55. artifact，可以考虑用tanstack query,  cached query结果； 避免反复请求;





完成：
8. aritifact:  支持图片、plotly、 pyecharts； 支持dataframe, 感觉 shadcn/ui的足够用了;
2. 旧的查询结果, 若param_values； 服务器要根据 report的modified, 文件的名字(ref), sessionId来生成hash;
4.  刷新页面，能还原当时的查询结果；
5.  session ID存储的是 param_values和file_contens， 和report的updatedTime；  刷新网页时， 还能重新还原；
6.  param values的读取和存储； 动态日期参数的解析， 都在前端； multiple_select， 不需要拼接了，为了页面能还原；
7. 多个datasource的存储， 是分多个文件还是单个文件；
9. 文件上传， 字段不匹配，要提示；
11. dataViz区域,   提供python代码；+数据
13. query处， 提供每个 datasource的解析后的代码；
14.  report需要维护 createTime, updateTime; 用于知道是否发生变更;
15. mul_input不能输入,
16. 级联参数中已经依赖了的dataSource；  不允许删除；
17.  viz区域的参数，会造成无限次渲染；
18. 删除文件时，不要真的删除；给表加上一个is_deleted就可以了
22. cascader是否生效了; 多对多怎么处理
23. close tab时，要清理一些数据
24. 换一下默认的文件路径， 让发布代码更方便。
25. 删除文件时， 文件的引用一起close
26. 关闭tab, dashboard没有正常响应
27. df_alias和option的key名，不能一样
28. cascader，应该是一颗树，不能多对多
29. 用户登录
30. 限制了数据查询的行数， 目前是5万
31. cascader取消即反选：
32.  plainParam， 单选不能为空；  且做好类型转换；
35. csv文件的处理
39. 重新query的时候， queryStatus, artifactResponse可以更新一下颜色; (INIT)
40. 网页刷新，进入到 /login, 为什么是白色页面
41. 后端多进程登陆
42. 后端多进程的lock问题
43. 后端的io读写，改为异步
44. 若不能复制剪切板，则改为下载
46. 隐藏参数按钮， 点击两次，没有加载当前的value；
47. navbar, item的文字溢出截断；
48. version管理: -> 没开发， 仅用了git来保存历史版本
50. date_range参数的支持。  比如  ${job_date:start}, ${job_date:end}
52. cascader推断， 需要支持 多对多；
56. 重新查询， 应该得消除 artifact params的values.
57. 级联单选，可以考虑，默认选第一个。
58. 支持类似dtale的功能
59. multiple_input：  支持复制粘贴,  逗号或回车分割







交互:
+------------+-----------------------+
|                  header            |
+------------+-----------------------+
|            |       tabs(2)         |
|  navbar(1) |  -------------------  |
|            |       param area(3)   |
|            |  ---------------------|
|            |       layout(4)       |
|            |                       |
|            |                       |
|            |                       |
|            |                       |
+------------+-----------------------+


交互动作， 影响了哪些页面:

1 ->  2, 3, 4:  点击文件，影响了activateTab
1 ->  2,  4:    文件改名, 影响了tab.title;   不一定是activateTab
1 ->  2, (3,4):  删除文件
      分支1 -> 影响了tabList, 若该文件不影响activateTab, 即  1 -> 2
      分支2 -> 影响了tabList, 若该文件还影响了activateTab, 即  1 -> 2, 3, 4


2 -> 3,4   点击了tab, 影响了activateTab
2 -> 3,4   切换tab, 影响了activateTab


3 -> 3, 4: 编辑report...  需要找一个地方存储updateTime
3 -> 4:    query, 影响了 queryStatus
3 -> 3:   参数更新， 文件上传等等； 仅影响了自己;

4 -> 4: option选择， 仅影响了自己


总结:
1. 核心的抓手:
    - activateTab
    - tab.title
    - tabsList
    - paramValues, paramFiles
    - queryStatus
    - 哪里存储 report的updateAt
2. param area和layout，需要memo, 根据activateTab更新;
3. 各区域需要的hook
    (1) navbar:
        - setActivateTab
        - setTabList (eg: 删除, 修改文件的操作)

        DONE:
            - memo
            - FileSystemItem的任何修改, 需要api同步; 已改为usecallback

    (2) tabs:
        - activateTab
        - tabsList
        - ps: 修改title， 不应该重新渲染  param area和layout

    (3) param area:
        - report
        - activateTab
        - paramValues
        - paramFiles
        - report.updateAt??
    (4) layout:
        - report
        - activateTab
        - queryStatus
```
