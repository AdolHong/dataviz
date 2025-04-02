from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime

class QueryBySourceRequest(BaseModel):
    fileId: str
    sourceId: str
    updateTime: datetime
    paramValues: Dict[str, Any]
    code: str
    dataContent: Optional[str] = None

class QueryResponse(BaseModel):
    status: str
    message: str
    error: Optional[str] = None
