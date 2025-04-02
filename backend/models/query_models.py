from pydantic import BaseModel
from typing import Dict, Any, Optional

class QueryBySourceRequest(BaseModel):
    fileId: str
    sourceId: str
    updateTime: str
    uniqueId: str
    paramValues: Optional[Dict[str, Any]] = None
    code: Optional[str] = None
    dataContent: Optional[str] = None

class QueryResponse(BaseModel):
    status: str
    message: str
    error: Optional[str] = None
