from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Dict, Any
from models.query_models import QueryBySourceRequest, QueryResponse
from models.report_models import Report
from utils.report_utils import get_report_content


execute_sql_query = lambda code, param_values, engine: print("hi sql")
execute_python_query = lambda code, param_values, engine: print("hi python")

router = APIRouter(tags=["query"])

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
            # execute_sql_query(
            #     request.code,
            #     request.paramValues,
            #     data_source.executor.engine
            # )
            print("??1")
            from engine_config import sql_engine
            result = sql_engine["default"](request.code)
            print("result", result)
            print("??2")
            
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

        return QueryResponse(
            status="success",
            message="Query executed successfully",
            data=result
        )

    except Exception as e:
        print("error", e)
        return QueryResponse(
            status="error",
            message=str(e),
            error=str(e)
        )