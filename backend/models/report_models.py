from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union, Literal

# UpdateMode 相关模型
class ManualUpdateMode(BaseModel):
    type: Literal["manual"]

class AutoUpdateMode(BaseModel):
    type: Literal["auto"]
    interval: Optional[int] = 600

UpdateMode = Union[ManualUpdateMode, AutoUpdateMode]

# Executor 相关模型
class PythonSourceExecutor(BaseModel):
    type: Literal["python"]
    engine: str
    code: str
    updateMode: UpdateMode

class SQLSourceExecutor(BaseModel):
    type: Literal["sql"]
    engine: str
    code: str
    updateMode: UpdateMode

class CSVSourceExecutor(BaseModel):
    type: Literal["csv_data"] 
    data: str

class CSVUploaderSourceExecutor(BaseModel):
    type: Literal["csv_uploader"]
    demoData: str

Executor = Union[PythonSourceExecutor, SQLSourceExecutor, CSVSourceExecutor, CSVUploaderSourceExecutor]

# DataSource 模型
class DataSource(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    alias: Optional[str] = None
    executor: Optional[Executor] = None
    config: Optional[Dict[str, Any]] = None

# Parameter 相关模型
class SingleSelectParamConfig(BaseModel):
    type: Literal["single_select"]
    choices: List[str]
    default: str

class MultiSelectParamConfig(BaseModel):
    type: Literal["multi_select"]
    choices: List[str]
    default: List[str]
    sep: str
    wrapper: str

class DatePickerParamConfig(BaseModel):
    type: Literal["date_picker"]
    dateFormat: str
    default: str

class MultiInputParamConfig(BaseModel):
    type: Literal["multi_input"]
    default: List[str]
    sep: str
    wrapper: str

class SingleInputParamConfig(BaseModel):
    type: Literal["single_input"]
    default: str

ParamConfig = Union[SingleSelectParamConfig, MultiSelectParamConfig, DatePickerParamConfig, MultiInputParamConfig, SingleInputParamConfig]

class Parameter(BaseModel):
    id: str
    name: str
    alias: Optional[str] = None
    description: Optional[str] = None
    config: ParamConfig

# Artifact 相关模型
class CascaderLevel(BaseModel):
    dfColumn: str
    name: Optional[str] = None
    description: Optional[str] = None

class CascaderParam(BaseModel):
    dfAlias: str
    levels: List[CascaderLevel]

class SinglePlainParam(BaseModel):
    type: Literal["single"]
    id: str
    name: str
    alias: Optional[str] = None
    description: Optional[str] = None
    valueType: Literal["string", "double", "boolean", "int"]
    default: str
    choices: List[str]

class MultiplePlainParam(BaseModel):
    type: Literal["multiple"]
    id: str
    name: str
    alias: Optional[str] = None
    description: Optional[str] = None
    valueType: Literal["string", "double", "boolean", "int"]
    default: List[str]
    choices: List[str]

ArtifactParam = Union[SinglePlainParam, MultiplePlainParam, CascaderParam]

class Artifact(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    code: str
    dependencies: List[str]
    executor_engine: str
    plainParams: Optional[List[Union[SinglePlainParam, MultiplePlainParam]]] = None
    cascaderParams: Optional[List[CascaderParam]] = None

# Layout 相关模型
class LayoutItem(BaseModel):
    id: str
    title: Optional[str] = None
    x: int = 0
    y: int = 0
    width: Optional[int] = None
    height: Optional[int] = None

class Layout(BaseModel):
    items: List[LayoutItem] = []
    columns: int = 1
    rows: int = 1

# Report 主模型
class Report(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    dataSources: List[DataSource] = []
    parameters: List[Parameter] = []
    artifacts: List[Artifact] = []
    layout: Layout
    createdAt: str
    updatedAt: str

    class Config:
        extra = "allow"  # 允许额外字段