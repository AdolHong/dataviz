from pydantic import BaseModel
from typing import Dict, Optional, List, Union, Literal
from models.query_models import Alert


class PlainParamValue(BaseModel):
    name: str
    type: Literal['single', 'multiple']
    value: Union[str, List[str]]
    valueType: Literal['string', 'double', 'boolean', 'int']


class ArtifactRequest(BaseModel):
    uniqueId: str
    dfAliasUniqueIds: Dict[str, str]
    plainParamValues: Dict[str, PlainParamValue]
    cascaderParamValues: Dict[str, Union[str, List[str]]]
    inferredParamValues: Dict[str, Union[str, List[str]]]
    pyCode: str
    engine: str


class ArtifactTextDataContext(BaseModel):
    type: Literal['text']
    data: str


class ArtifactImageDataContext(BaseModel):
    type: Literal['image']
    data: str


class ArtifactTableDataContext(BaseModel):
    type: Literal['table']
    data: str


class ArtifactPlotlyDataContext(BaseModel):
    type: Literal['plotly']
    data: str


class ArtifactEChartDataContext(BaseModel):
    type: Literal['echart']
    data: str


class ArtifactAltairDataContext(BaseModel):
    type: Literal['altair']
    data: str


ArtifactDataContext = Union[
    ArtifactTextDataContext,
    ArtifactImageDataContext,
    ArtifactTableDataContext,
    ArtifactPlotlyDataContext,
    ArtifactEChartDataContext,
    ArtifactAltairDataContext
]


class ArtifactCodeContext(BaseModel):
    uniqueId: str
    dfAliasUniqueIds: Dict[str, str]
    plainParamValues: Dict[str, PlainParamValue]
    cascaderParamValues: Dict[str, Union[str, List[str]]]
    inferredParamValues: Dict[str, Union[str, List[str]]]
    pyCode: str
    engine: str


class ArtifactResponse(BaseModel):
    status: str
    message: str
    error: str = ""
    alerts: List[Alert] = []
    codeContext: ArtifactCodeContext
    dataContext: Optional[ArtifactDataContext] = None
    queryTime: str


class ArtifactCodeResponse(BaseModel):
    status: str
    message: str
    error: str = ""
    alerts: List[Alert] = []
    pyCode: str
    queryTime: str
