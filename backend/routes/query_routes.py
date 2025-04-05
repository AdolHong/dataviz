import json
import os
from fastapi import APIRouter, HTTPException, Depends, Header
from datetime import datetime
from typing import Dict, Any, Optional, List
from models.query_models import QueryRequest, QueryResponse, QueryResponseDataContext, QueryResponseCodeContext, Alert
from models.report_models import Report
from utils.report_utils import get_report_content
from pathlib import Path
from utils.fs_utils import FILE_CACHE_PATH
import pandas as pd
from routes.auth_routes import verify_token_dependency

import pandas as pd
from io import StringIO


execute_sql_query = lambda code, param_values, engine: print("hi sql")
execute_python_query = lambda code, param_values, engine: print("hi python")

router = APIRouter(tags=["query"])

def save_query_result(uniqueId:str, result:str):
    with open(Path(FILE_CACHE_PATH) / f"{uniqueId}.data", "w") as f:
        json.dump(json.loads(result), f)

def load_query_result(uniqueId:str)->pd.DataFrame:
    with open(Path(FILE_CACHE_PATH)/ "cachedData"  / f"{uniqueId}.data", "r") as f:
        return pd.read_json(f)


@router.post("/query_by_source_id", response_model=QueryResponse)
async def query_by_source_id(request: QueryRequest, username: str = Depends(verify_token_dependency)):
    """
    根据数据源ID执行查询，需要验证token
    """
    alerts = []
    code_context = construct_response_code_context(request, request.uniqueId)
    try:
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
        
        # 创建data context
        data_context = QueryResponseDataContext(
            uniqueId=request.uniqueId,
            demoData= '' if result is None or (isinstance(result, pd.DataFrame) and result.empty) else convert_df_to_csv_string(result.head(5)),
            rowNumber=len(result) if result is not None else 0,
        )
        
        # 构造codeContext
        code_context = construct_response_code_context(request, request.uniqueId)
        # 构造cascaderContext
        cascader_context = construct_response_cascader_context(result, request.cascaderContext.required)
        return QueryResponse(
            status="success",
            message="Query executed successfully",
            error="",
            alerts=alerts,
            data=data_context,
            codeContext=code_context,
            cascaderContext=cascader_context,
            queryTime=datetime.now().isoformat()
        )

    except Exception as e:
        return QueryResponse(
            status="error",
            message=str(e),
            codeContext=code_context,   
            error=str(e),
            queryTime=datetime.now().isoformat(),
            alerts=[Alert(type="error", message=str(e))],
        )

# 同样修改获取查询结果的接口，使用依赖注入进行token验证
@router.get("/query_result/{query_hash}")
async def get_query_result(query_hash: str, session_id: str, username: str = Depends(verify_token_dependency)):
    """
    根据查询哈希获取缓存的查询结果，需要验证token
    """
    # 处理查询逻辑
    try:
        # 这里应该是原来的获取缓存查询结果的逻辑
        pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def convert_df_to_csv_string(df: pd.DataFrame):
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False, encoding='utf-8')
    return csv_buffer.getvalue()



def check_unique_parents(df, columns):
    """
    Function to check if all child nodes correspond to unique parent nodes.

    Parameters:
        df (pd.DataFrame): The pandas DataFrame containing the data.
        parent_columns (list): List of column names representing parent nodes.
        child_column (str): Column name representing child nodes.

    Returns:
        bool: True if all child nodes have unique parent nodes, False otherwise.
    """
    parent_columns = columns[:len(columns) - 1]
    child_column = columns[- 1]


    # Group by child column and count unique combinations of parent columns
    grouped = df.groupby(child_column)[parent_columns].nunique()

    # Check if any child has more than one unique parent combination
    for col in parent_columns:
        if (grouped[col] > 1).any():
            return False, grouped[grouped[col] > 1].head(5)
    return True, None

def construct_response_cascader_context(df: Optional[pd.DataFrame], cascader_required: List[str]):
    # 空数据
    if df is None or not isinstance(df, pd.DataFrame):
        raise ValueError("[CascaderContext] DataFrame is None")
    
    # 检查列是否存在
    cascader_tuples = []
    for cascader_tuple in cascader_required:
        columns = json.loads(cascader_tuple)
        for column in columns:
            if column not in df.columns:
                raise ValueError(f"[CascaderContext] Column {column} not found in DataFrame")
        cascader_tuples.append(columns)
    
    # 推断出cascader的值
    inferred_cascader = {}
    if df.empty:
        for required, columns in zip(cascader_required, cascader_tuples):
            inferred_cascader[required] = ",".join(columns) + "\n"
    else:
        for required, columns in zip(cascader_required, cascader_tuples):
            df_unique = df[columns].drop_duplicates()
            flag_unique, df_bad_case = check_unique_parents(df_unique, columns)
            if not flag_unique:
                raise ValueError(f"[CascaderContext] {columns} 存在一个子结点对应多个父结点: {str(df_bad_case)}")
            inferred_cascader[required] = convert_df_to_csv_string(df_unique)
    return {
        "required": cascader_required,
        "inferred": inferred_cascader
    }

def construct_response_code_context(request: QueryRequest, uniqueId:str):
    # 根据不同的请求类型构建 QueryResponseCodeContext
    if request.requestContext.type == 'sql':
        return QueryResponseCodeContext(
            uniqueId=uniqueId,
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
            uniqueId=uniqueId,
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
            uniqueId=uniqueId,
            fileId=request.requestContext.fileId,
            sourceId=request.requestContext.sourceId,
            reportUpdateTime=request.requestContext.reportUpdateTime,
            type='csv_data'
        )
    elif request.requestContext.type == 'csv_uploader':
        return QueryResponseCodeContext(
            uniqueId=uniqueId,
            fileId=request.requestContext.fileId,
            sourceId=request.requestContext.sourceId,
            reportUpdateTime=request.requestContext.reportUpdateTime,
            type='csv_uploader'
        )
    else:
        raise ValueError(f"Unsupported request type: {request.requestContext.type}")