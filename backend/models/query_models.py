from pydantic import BaseModel
from typing import Dict, Any, Optional

class QueryBySourceRequest(BaseModel):
    fileId: str
    sourceId: str
    updateTime: str
    paramValues: Dict[str, Any]
    code: str
    dataContent: Optional[str] = None

class QueryResponse(BaseModel):
    status: str
    message: str
    error: Optional[str] = None
