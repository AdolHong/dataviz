import os
from pathlib import Path
import socket
import aiomysql
import pandas as pd
from typing import Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
import duckdb


def execute_duckdb_query_sync(query: str):
    """同步执行 DuckDB 查询的函数"""
    # 数据库文件路径
    DB_PATH = Path(__file__).parent / "data" / "demodata.duckdb"

    # 确保数据目录存在
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = duckdb.connect(str(DB_PATH))
    try:
        result = conn.execute(query).fetchdf()
        return result
    except Exception as e:
        raise e
    finally:
        conn.close()


async def execute_duckdb_query(query: str):
    """异步执行 DuckDB 查询的函数"""
    # 使用线程池执行同步查询
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(
            pool,
            execute_duckdb_query_sync,
            query
        )
    return result


async def pd_read_sql(query: str, url: str, prepare_stmt: Optional[str] = None) -> pd.DataFrame:
    """异步执行SQL查询并返回DataFrame"""
    conn = await aiomysql.connect(
        host=url.split('//')[1].split(':')[0],
        port=int(url.split(':')[-1].split('/')[0]),
        user=url.split('//')[1].split(':')[1].split('@')[0],
        password=url.split('//')[1].split(':')[1].split('@')[1].split('/')[0],
        db=url.split('/')[-1],
        autocommit=True
    )

    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            if prepare_stmt:
                await cursor.execute(prepare_stmt)

            await cursor.execute(query)
            result = await cursor.fetchall()

            # 将结果转换为DataFrame
            df = pd.DataFrame(result)
            return df
    except Exception as e:
        raise Exception(f"SQL查询错误: {e}")
    finally:
        conn.close()


async def execute_query(query: str, url: Optional[str] = None):
    """根据主机名选择执行查询的方法"""
    if socket.gethostname() == "Jiahaos-MacBook-Pro.local":
        # 如果是本地开发环境，使用异步 DuckDB 查询
        return await execute_duckdb_query(query)
    else:
        return await pd_read_sql(query, url, prepare_stmt='set query_mem_limit = 68719476736')

# 异步查询引擎
sql_engine = {
    "default": lambda query, url: execute_query(query, url),
}
