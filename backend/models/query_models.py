from pydantic import BaseModel
from typing import Dict, Any, Optional, List, Union, Literal

class CascaderContext(BaseModel):
    required: List[str]
    inferred: Optional[Dict[str, str]] = None

class Alert(BaseModel):
    type: Literal['info', 'warning', 'error']
    message: str
class QueryResponseDataContext(BaseModel):
    rowNumber: int = 0
    demoData: str = ""
    uniqueId: str
    

class QueryResponseCodeContext(BaseModel):
    uniqueId:str
    fileId: str
    sourceId: str
    reportUpdateTime: str
    type: Literal['sql', 'python', 'csv_data', 'csv_uploader']
    engine: Optional[str] = None
    code: Optional[str] = None
    parsedCode: Optional[str] = None
    paramValues: Optional[Dict[str, Any]] = None

class QueryResponse(BaseModel):
    status: str
    message: str
    error: str = ""
    alerts: List[Alert] = []
    data: Optional[QueryResponseDataContext] = None
    codeContext: Optional[QueryResponseCodeContext] = None
    cascaderContext: Optional[CascaderContext] = None
    queryTime: str

class QueryBySQLRequestContext(BaseModel):
    type: Literal['sql']
    fileId: str
    sourceId: str
    reportUpdateTime: str
    engine: str
    code: str
    parsedCode: str
    paramValues: Optional[Dict[str, Any]] = None

class QueryByPythonRequestContext(BaseModel):
    type: Literal['python']
    fileId: str
    sourceId: str
    reportUpdateTime: str
    engine: str
    code: str
    parsedCode: str
    paramValues: Optional[Dict[str, Any]] = None

class QueryByCsvDataRequestContext(BaseModel):
    type: Literal['csv_data']
    fileId: str
    sourceId: str
    reportUpdateTime: str

class QueryByCsvUploadRequestContext(BaseModel):
    type: Literal['csv_uploader']
    fileId: str
    sourceId: str
    reportUpdateTime: str
    dataContent: str



class QueryRequest(BaseModel):
    uniqueId: str
    requestContext: Union[
        QueryBySQLRequestContext, 
        QueryByPythonRequestContext, 
        QueryByCsvDataRequestContext, 
        QueryByCsvUploadRequestContext
    ]
    cascaderContext: CascaderContext
