from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Dict, Any
from models.query_models import QueryBySourceRequest, QueryResponse
from models.report_models import Report
from utils.fs_utils import  get_report_content, find_item_by_id

execute_sql_query = None
execute_python_query = None

router = APIRouter()

@router.post("/query_by_source_id", response_model=QueryResponse)
async def query_by_source_id(request: QueryBySourceRequest):
    """
    根据数据源ID执行查询
    """
    try:
        # 获取报表信息
        report_content = get_report_content(request.fileId)
        if not report_content:
            return QueryResponse(
                status="error",
                message="Report not found",
                error="Report not found"
            )

        # 检查更新时间是否匹配
        report_update_time = datetime.fromisoformat(report.updatedAt)
        if report_update_time != request.update_time:
            return QueryResponse(
                status="error",
                message="Report has been updated, please refresh the page",
                error="Report version mismatch"
            )

        # 查找对应的数据源
        data_source = next(
            (ds for ds in report.dataSources if ds.id == request.fileId),
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
            result = await execute_sql_query(
                request.code,
                request.param_values,
                data_source.executor.engine
            )
        elif data_source.executor.type == "python":
            result = await execute_python_query(
                request.code,
                request.param_values,
                request.data,
                data_source.executor.engine
            )
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
        return QueryResponse(
            status="error",
            message=str(e),
            error=str(e)
        )