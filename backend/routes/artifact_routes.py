import json
from fastapi import APIRouter
from pathlib import Path
import pandas as pd
import io
import io
import base64
from typing import Literal, Any
from datetime import datetime
from utils.fs_utils import FILE_CACHE_PATH
from contextlib import redirect_stdout
from functools import reduce


from models.artifact_models import ArtifactRequest, ArtifactResponse, ArtifactCodeContext, ArtifactTextDataContext, ArtifactPlotlyDataContext, ArtifactEChartDataContext, ArtifactImageDataContext, ArtifactAltairDataContext, ArtifactCodeResponse, ArtifactTableDataContext
from models.query_models import Alert
from models.artifact_models import PlainParamValue

router = APIRouter(tags=["artifact"])


def load_query_result(uniqueId: str) -> pd.DataFrame:
    """加载查询结果"""
    try:
        with open(Path(FILE_CACHE_PATH) / f"{uniqueId}.data", "r") as f:
            return pd.read_json(f)
    except Exception as e:
        raise ValueError(f"Failed to load query result: {str(e)}")


def convert_plain_param_value(value: str, valueType: Literal['string', 'double', 'boolean', 'int']) -> Any:
    try:
        """转换普通参数值"""
        if valueType == 'string':
            return str(value)
        elif valueType == 'double':
            return float(value)
        elif valueType == 'boolean':
            return bool(value)
        elif valueType == 'int':
            return int(value)
    except Exception as e:
        raise ValueError(
            f"[PARAMS] Invalid plain param value: {value}, should be a {valueType}, with error: {str(e)}")


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
                    alerts=[
                        Alert(type="error", message=f"Failed to load data source {alias}: {str(e)}")],
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
        for param_name, param_values in request.cascaderParamValues.items():
            df_alias, df_columns = param_name.split(
                ",")[0], param_name.split(",")[1:]

            # 对于cascader_params, 如果参数值为空, 则默认为全选
            if len(param_values) == 0:
                continue

            df_selected_list = []
            for param_value in param_values:

                conds = [dfs[df_alias][column].astype(str) == param_value[idx] for idx, column in enumerate(
                    df_columns) if idx < len(param_value)]
                df_index = reduce(lambda x, y: x & y, conds)
                df_selected_list.append(dfs[df_alias].loc[df_index])
            dfs[df_alias] = pd.concat(df_selected_list)

        # 对于inferred_params, 进行类型转换
        for param_name, param_value in request.inferredParamValues.items():
            df_alias, df_column = param_name.split('.')[:2]
            df_index = dfs[df_alias][df_column].fillna(
                '').astype(str).str.lower().isin(param_value)
            dfs[df_alias] = dfs[df_alias].loc[df_index]

        # 对于plain_params, 进行类型转换
        plain_param_values = {}
        for param_name, param_value in request.plainParamValues.items():
            if isinstance(param_value, PlainParamValue) and param_value.type == 'single' and isinstance(param_value.value, str):
                plain_param_values[param_name] = convert_plain_param_value(
                    param_value.value, param_value.valueType)
            elif isinstance(param_value, PlainParamValue) and param_value.type == 'multiple' and isinstance(param_value.value, list):
                plain_param_values[param_name] = [convert_plain_param_value(
                    value, param_value.valueType) for value in param_value.value]
            else:
                raise ValueError(
                    f"[PARAMS] Invalid plain param value: {param_value}, should be a list or a string.")

        # 创建本地变量空间，包含DataFrame对象和参数
        local_vars = {
            **dfs,  # 数据源
            **plain_param_values
        }

        # 创建输出捕获
        text_output = io.StringIO()
        try:
            with redirect_stdout(text_output):
                exec(code, local_vars)
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
                data_context = ArtifactTextDataContext(
                    type="text", data=result)
            # elif isinstance(result, plotly.graph_objs._figure.Figure):
            elif 'plotly' in str(type(result)):
                data_context = ArtifactPlotlyDataContext(
                    type="plotly", data=result.to_json())
            elif 'pyecharts' in str(type(result)):
                data_context = ArtifactEChartDataContext(
                    type="echart", data=result.dump_options())
            elif 'matplotlib' in str(type(result)):
                # 将图表保存为BytesIO对象
                buf = io.BytesIO()
                result.savefig(buf, format='png')
                buf.seek(0)
                base64_image = base64.b64encode(buf.read()).decode('utf-8')
                buf.close()
                data_context = ArtifactImageDataContext(
                    type="image", data=base64_image)
            elif 'altair' in str(type(result)):
                data_context = ArtifactAltairDataContext(
                    type="altair", data=json.dumps(result.to_dict()))
            elif "pandas.core.frame.DataFrame" in str(type(result)):
                data_context = ArtifactTableDataContext(
                    type="table", data=result.to_json(orient='records', date_format='iso', force_ascii=False))
            else:
                # 默认转换为文本
                data_context = ArtifactTextDataContext(
                    type="text", data=str(result))
        else:
            # 如果没有result变量，返回标准输出内容
            if captured_output:
                data_context = ArtifactTextDataContext(
                    type="text", data=captured_output)
            else:
                data_context = None
                alerts.append(
                    Alert(type="warning", message="No result or output from code execution"))

    except Exception as e:
        return ArtifactResponse(
            queryTime=datetime.now().isoformat(),
            status="error",
            message=f"Failed to execute Python code",
            error=str(e),
            alerts=[
                Alert(type="error", message=f"Code execution error: {str(e)}")],
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


@router.post("/artifact_code", response_model=ArtifactCodeResponse)
async def artifact_code(request: ArtifactRequest):
    """
    处理代码并返回格式化后的Python代码，用于复制到剪贴板
    """
    alerts = []
    # 加载所有依赖的数据源查询结果
    dfs = {}
    for alias, uniqueId in request.dfAliasUniqueIds.items():
        try:
            df = load_query_result(uniqueId)
            dfs[alias] = df
        except Exception as e:
            return ArtifactCodeResponse(
                queryTime=datetime.now().isoformat(),
                status="error",
                message=f"[PYTHON]Failed to load data source {alias}: {str(e)}",
                error=str(e),
                alerts=[
                    Alert(type="error", message=f"Failed to load data source {alias}: {str(e)}")],
                pyCode=""
            )
    try:
        # cascader_params 处理
        for param_name, param_value in request.cascaderParamValues.items():

            print(param_name, param_value)
            # if not isinstance(param_value, list):
            #     raise ValueError(
            #         f"[PARAMS] Invalid cascader param value: {param_value}, should be a list.")

            # # 对于cascader_params, 如果参数值为空, 则默认为全选
            # if len(param_value) == 0:
            #     continue
            # df_alias, df_columns = param_name.split(
            #     ",")[0], param_name.split(",")[1:]

            # print(f"df_alias: {df_alias}, df_columns: {df_columns}")
            # print(f"param_value: {param_value}")

            # df_index = dfs[df_alias][df_columns].fillna(
            #     '').astype(str).str.lower().isin(param_value)

            # dfs[df_alias] = dfs[df_alias].loc[df_index]

        # 对于inferred_params, 进行类型转换
        for param_name, param_value in request.inferredParamValues.items():
            df_alias, df_column = param_name.split('.')[:2]
            df_index = dfs[df_alias][df_column].fillna(
                '').astype(str).str.lower().isin(param_value)
            dfs[df_alias] = dfs[df_alias].loc[df_index]

        # 对于plain_params, 进行类型转换
        plain_param_values = {}
        for param_name, param_value in request.plainParamValues.items():
            if isinstance(param_value, PlainParamValue) and param_value.type == 'single' and isinstance(param_value.value, str):
                plain_param_values[param_name] = convert_plain_param_value(
                    param_value.value, param_value.valueType)
            elif isinstance(param_value, PlainParamValue) and param_value.type == 'multiple' and isinstance(param_value.value, list):
                plain_param_values[param_name] = [convert_plain_param_value(
                    value, param_value.valueType) for value in param_value.value]
            else:
                raise ValueError(
                    f"[PARAMS] Invalid plain param value: {param_value}, should be a list or a string.")

        print(1)
        # import
        import_context = "# import\n" + "import io\n" + \
            "import json\n" + "import pandas as pd\n"
        print(2)
        # data
        data_context = "# data\n" + \
            "\n".join([f"{df_alias} = pd.read_json(io.StringIO({repr(df_value.to_json(orient='records', date_format='iso', force_ascii=False).strip())}))" for df_alias, df_value in dfs.items()])
        print(3)
        # param
        params_context = "# params\n" + \
            f"globals().update(json.loads(\"\"\"{json.dumps(plain_param_values)}\"\"\"))"
        pyCode = import_context + "\n\n" + params_context + "\n\n" + \
            data_context + "\n\n" + "# code\n" + request.pyCode
    except Exception as e:
        return ArtifactCodeResponse(
            queryTime=datetime.now().isoformat(),
            status="error",
            message=f"Failed to process Python code",
            error=str(e),
            alerts=[
                Alert(type="error", message=f"Code processing error: {str(e)}")],
            pyCode=""
        )

    # 返回处理结果
    return ArtifactCodeResponse(
        status="success",
        message="Code processed successfully",
        alerts=alerts,
        pyCode=pyCode,
        queryTime=datetime.now().isoformat()
    )
