import json
import os
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Dict, Any
from models.query_models import QueryBySourceRequest, QueryResponse
from models.report_models import Report
from utils.report_utils import get_report_content
from pathlib import Path
import pandas as pd

execute_sql_query = lambda code, param_values, engine: print("hi sql")
execute_python_query = lambda code, param_values, engine: print("hi python")

router = APIRouter(tags=["query"])

def save_query_result(uniqueId:str, result:str):
    os.makedirs(Path(__file__).parent.parent / "cachedData", exist_ok=True)
    with open(Path(__file__).parent.parent / "cachedData"  / f"{uniqueId}.data", "w") as f:
        json.dump(json.loads(result), f)

def load_query_result(uniqueId:str)->pd.DataFrame:
    with open(Path(__file__).parent.parent / "cachedData"  / f"{uniqueId}.data", "r") as f:
        return pd.read_json(f)


@router.post("/query_by_source_id", response_model=QueryResponse)
async def query_by_source_id(request: QueryBySourceRequest):
    """
    根据数据源ID执行查询
    """
    try:

        print("uniqueId", request.uniqueId)
        # 根据report id 获取报表信息
        report = get_report_content(request.fileId)
        if not report:
            return QueryResponse(
                status="error",
                message="Report not found",
                error="Report not found"
            )

        # 检查更新时间是否匹配
        if report.updatedAt != request.updateTime:
            return QueryResponse(
                status="error",
                message="Report has been updated, please refresh the page",
                error="Report version mismatch"
            )

        # 查找对应的数据源
        data_source = next(
            (ds for ds in report.dataSources if ds.id == request.sourceId),
            None
        )
        
        if not data_source:
            return QueryResponse(
                status="error",
                message="Data source not found",
                error="Data source not found"
            )

        # 根据数据源类型执行不同的查询
        result = None
        if data_source.executor.type == "sql":

            print("sql code: ", request.code)
            # execute_sql_query(
            #     request.code,
            #     request.paramValues,
            #     data_source.executor.engine
            # )
            from engine_config import sql_engine
            result = sql_engine[data_source.executor.engine](request.code)
        elif data_source.executor.type == "python":
            execute_python_query(
                request.code,
                request.paramValues,
                data_source.executor.engine
            )
        elif data_source.executor.type == "csv_uploader":
            print("todo: uploader")
        elif data_source.executor.type == "csv_data":
            print("todo: csv_data")
        else:
            return QueryResponse(
                status="error",
                message="Unsupported executor type",
                error=f"Unsupported executor type: {data_source.executor.type}"
            )
        
        if result is not None:
            save_query_result(request.uniqueId, result.to_json(orient='records'))


        return QueryResponse(
            status="success",
            message="Query executed successfully",
            data=None
        )

    except Exception as e:
        print("error", e)
        return QueryResponse(
            status="error",
            message=str(e),
            error=str(e)
        )