import json
import os
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Dict, Any
from models.query_models import QueryRequest, QueryResponse, QueryResponseDataContext, QueryResponseCodeContext, Alert
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
async def query_by_source_id(request: QueryRequest):
    """
    根据数据源ID执行查询
    """
    alerts = []
    try:
        print("uniqueId", request.uniqueId)
        # 根据report id 获取报表信息
        report = get_report_content(request.requestContext.fileId)
        if not report:
            return QueryResponse(
                status="error",
                message="Report not found",
                error="Report not found",
                alerts=[Alert(type="error", message="Report not found")]
            )

        # 检查更新时间是否匹配
        if report.updatedAt != request.requestContext.reportUpdateTime:
            return QueryResponse(
                status="error",
                message="Report has been updated, please refresh the page",
                error="Report version mismatch",
                alerts=[Alert(type="error", message="Report version mismatch")]
            )

        # 查找对应的数据源
        data_source = next(
            (ds for ds in report.dataSources if ds.id == request.requestContext.sourceId),
            None
        )
    
        # 若找不到datasource，则返回错误
        if not data_source:
            return QueryResponse(
                status="error",
                message="Data source not found",
                error="Data source not found",
                alerts=[Alert(type="error", message="Data source not found")]
            )

        # 根据数据源类型执行不同的查询
        result = None
        request_type = request.requestContext.type
        
        if request_type == "sql":
            code = request.requestContext.parsedCode
            engine = request.requestContext.engine
            
            print("sql code: ", code)
            # 执行SQL查询
            from engine_config import sql_engine
            result = sql_engine[engine](code)
            
        elif request_type == "python":
            code = request.requestContext.parsedCode
            engine = request.requestContext.engine
            
            execute_python_query(
                code,
                {},
                engine
            )
            
        elif request_type == "csv_uploader":
            dataContent = request.requestContext.dataContent
            print("todo: uploader")
            
        elif request_type == "csv_data":
            print("todo: csv_data")
            
        else:
            return QueryResponse(
                status="error",
                message="Unsupported executor type",
                error=f"Unsupported executor type: {request_type}",
                alerts=[Alert(type="error", message=f"Unsupported executor type: {request_type}")]
            )
        
        if result is not None:
            save_query_result(request.uniqueId, result.to_json(orient='records'))

        # 创建响应
        data_context = QueryResponseDataContext(
            uniqueId=request.uniqueId,
            demoData="",
            rowNumber=len(result) if result is not None else 0,
            cascaderContext={}
        )
        
        # 构造codeContext
        code_context = construct_response_code_context(request)

        return QueryResponse(
            status="success",
            message="Query executed successfully",
            error="",
            alerts=alerts,
            data=data_context,
            codeContext=code_context,
            queryTime=datetime.now().isoformat()
        )

    except Exception as e:
        print("error", e)
        return QueryResponse(
            status="error",
            message=str(e),
            error=str(e),
            alerts=[Alert(type="error", message=str(e))]
        )
        
def construct_response_code_context(request: QueryRequest):
    # 根据不同的请求类型构建 QueryResponseCodeContext
    if request.requestContext.type == 'sql':
        return QueryResponseCodeContext(
            fileId=request.requestContext.fileId,
            sourceId=request.requestContext.sourceId,
            reportUpdateTime=request.requestContext.reportUpdateTime,
            type='sql',
            engine=request.requestContext.engine,
            code=request.requestContext.code,
            parsedCode=request.requestContext.parsedCode,
            paramValues=request.requestContext.paramValues
        )
    elif request.requestContext.type == 'python':
        return QueryResponseCodeContext(
            fileId=request.requestContext.fileId,
            sourceId=request.requestContext.sourceId,
            reportUpdateTime=request.requestContext.reportUpdateTime,
            type='python',
            engine=request.requestContext.engine,
            code=request.requestContext.code,
            parsedCode=request.requestContext.parsedCode,
            paramValues=request.requestContext.paramValues
        )
    elif request.requestContext.type == 'csv_data':
        return QueryResponseCodeContext(
            fileId=request.requestContext.fileId,
            sourceId=request.requestContext.sourceId,
            reportUpdateTime=request.requestContext.reportUpdateTime,
            type='csv_data'
        )
    elif request.requestContext.type == 'csv_uploader':
        return QueryResponseCodeContext(
            fileId=request.requestContext.fileId,
            sourceId=request.requestContext.sourceId,
            reportUpdateTime=request.requestContext.reportUpdateTime,
            type='csv_uploader'
        )
    else:
        raise ValueError(f"Unsupported request type: {request.requestContext.type}")