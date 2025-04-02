

import duckdb
import os
from pathlib import Path


def get_connection():
    import socket
    if socket.gethostname() == "Jiahaos-MacBook-Pro.local":
        # 数据库文件路径
        DB_PATH = Path(__file__).parent / "data" / "demodata.duckdb"

        # 确保数据目录存在
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

        # 开发环境, 获取DuckDB连接
        return duckdb.connect(str(DB_PATH))
    else:
        pass
    
    

def execute_duckdb_query(query: str, params=None):
    """执行SQL查询并返回结果"""
    conn = get_connection()
    try:
        
        result = conn.execute(query).fetchdf()
        return result
    except Exception as e:
        raise e
    finally:
        conn.close()

def pd_read_sql(url, query, prepare_stmt=None):
    from sqlalchemy import create_engine, text
    import pandas as pd
    engine = create_engine(url)
    # with语句， 避免忘记close connection
    with engine.connect() as con:
        if prepare_stmt is not None:
            con.exec_driver_sql(prepare_stmt)

        # query = text(query).execution_options(no_parameters=True)
        query = text(query)
        df = pd.read_sql_query(query, con=con)
    return df

def execute_mysql_query(query, url, prepare_stmt=None):
    import pandas as pd
    engine = lambda query: pd_read_sql(url, query, prepare_stmt=prepare_stmt)

    try:
        # print("type:", type(query))
        df = engine(query)
    except Exception as e:
        df = pd.DataFrame([{"error": str(e)}])
    return df

def execute_query(query: str, params=None):
    import socket
    if socket.gethostname() == "Jiahaos-MacBook-Pro.local":
        return execute_duckdb_query(query,params)
    else:
        url = ""
        return execute_mysql_query(query,url, prepare_stmt='set query_mem_limit = 68719476736')


sql_engine = {
    "default": execute_query,
}
