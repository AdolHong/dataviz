import json
import os
from fastapi import APIRouter
from pathlib import Path
import pandas as pd
import io
import plotly
import pyecharts
import io
import base64
import matplotlib.pyplot as plt
from datetime import datetime
from utils.fs_utils import FILE_CACHE_PATH


from models.artifact_models import ArtifactRequest, ArtifactResponse, ArtifactCodeContext, ArtifactTextDataContext, ArtifactPlotlyDataContext, ArtifactEChartDataContext, ArtifactImageDataContext,ArtifactAltairDataContext
from models.query_models import Alert

router = APIRouter(tags=["artifact"])

def load_query_result(uniqueId: str) -> pd.DataFrame:
    """加载查询结果"""
    try:
        with open(Path(FILE_CACHE_PATH) / f"{uniqueId}.data", "r") as f:
            return pd.read_json(f)
    except Exception as e:
        raise ValueError(f"Failed to load query result: {str(e)}")

@router.post("/execute_artifact", response_model=ArtifactResponse)
async def execute_artifact(request: ArtifactRequest):
    """
    执行可视化代码并返回结果
    """
    alerts = []
    try:
        # 加载所有依赖的数据源查询结果
        dfs = {}
        for alias, uniqueId in request.dfAliasUniqueIds.items():
            try:
                df = load_query_result(uniqueId)
                dfs[alias] = df
            except Exception as e:
                return ArtifactResponse(
                    queryTime=datetime.now().isoformat(),
                    status="error",
                    message=f"[PYTHON]Failed to load data source {alias}: {str(e)}",
                    error=str(e),
                    alerts=[Alert(type="error", message=f"Failed to load data source {alias}: {str(e)}")],
                    codeContext=ArtifactCodeContext(**request.dict())
                )
        # 构建代码执行环境
        code = request.pyCode
        engine = request.engine
        
        # 判断引擎
        result = None
        if engine != "default":
            raise ValueError(f"Unsupported engine: {engine}")
            # 执行Python代码
    except Exception as e:
        return ArtifactResponse(
            queryTime=datetime.now().isoformat(),
            status="error",
            message=str(e),
            error=str(e),
            alerts=[Alert(type="error", message=str(e))],
            codeContext=ArtifactCodeContext(**request.dict())
        )
        
    try:
        # cascader_params 处理
        for param_name, param_value in request.cascaderParamValues.items():
            if not isinstance(param_value, list):
                raise ValueError(f"Invalid cascader param value: {param_value}, should be a list.")
            
            # 对于cascader_params, 如果参数值为空, 则默认为全选
            if len(param_value) == 0:
                continue
            df_alias, df_column = param_name.split(",")[:2]
            df_index = dfs[df_alias][df_column].astype(str).isin(param_value)
            dfs[df_alias] = dfs[df_alias].loc[df_index]
            
            
        # 创建本地变量空间，包含DataFrame对象和参数
        local_vars = {
            **dfs,  # 数据源
            **request.plainParamValues
        }
        
        
        # 创建输出捕获
        text_output = io.StringIO()
        try:
            # 执行代码，捕获标准输出
            exec_globals = {
                "pd": pd,
                "print": lambda *args, **kwargs: print(*args, **kwargs, file=text_output)
            }
            exec(code, exec_globals, local_vars)
        except Exception as e:
            return ArtifactResponse(
                queryTime=datetime.now().isoformat(),
                status="error",
                message=text_output.getvalue(),
                error=f"[PYTHON CODE] {type(e)}: " + str(e),
                alerts=[Alert(type="error", message=str(e))],
                codeContext=ArtifactCodeContext(**request.dict())
            )
        # 获取捕获的输出
        captured_output = text_output.getvalue()
        # 检查是否有输出结果变量
        if "result" in local_vars:
            result = local_vars["result"]
            
        
            # 根据结果类型返回不同的数据上下文
            if isinstance(result, str):
                data_context = ArtifactTextDataContext(type="text", data=result)
            # elif isinstance(result, plotly.graph_objs._figure.Figure):
            elif 'plotly' in str(type(result)):
                data_context = ArtifactPlotlyDataContext(type="plotly", data=result.to_json())
            elif 'pyecharts' in str(type(result)):
                data_context = ArtifactEChartDataContext(type="echart", data=result.dump_options())
            elif 'matplotlib' in str(type(result)):
                # 将图表保存为BytesIO对象
                buf = io.BytesIO()
                result.savefig(buf, format='png')
                buf.seek(0)
                base64_image = base64.b64encode(buf.read()).decode('utf-8')
                buf.close()
                data_context = ArtifactImageDataContext(type="image", data=base64_image)
            elif 'altair' in str(type(result)):
                data_context = ArtifactAltairDataContext(type="altair", data=json.dumps(result.to_dict()))
            else:
                # 默认转换为文本
                data_context = ArtifactTextDataContext(type="text", data=str(result))
        else:
            # 如果没有result变量，返回标准输出内容
            if captured_output:
                data_context = ArtifactTextDataContext(type="text", data=captured_output)
            else:
                data_context = None
                alerts.append(Alert(type="warning", message="No result or output from code execution"))
        
    except Exception as e:
        return ArtifactResponse(
            queryTime=datetime.now().isoformat(),
            status="error",
            message=f"Failed to execute Python code",
            error=str(e),
            alerts=[Alert(type="error", message=f"Code execution error: {str(e)}")],
            codeContext=ArtifactCodeContext(**request.dict())
        )
         

                
    # 返回执行结果
    return ArtifactResponse(
        status="success",
        message=captured_output if captured_output else "Artifact executed successfully",
        alerts=alerts,
        codeContext=ArtifactCodeContext(**request.dict()),
        dataContext=data_context,
        queryTime=datetime.now().isoformat()
    )
        
