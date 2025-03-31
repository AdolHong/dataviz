from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class UpdateMode(BaseModel):
    type: str

class Executor(BaseModel):
    type: str
    engine: str
    code: str
    updateMode: UpdateMode

class DataSource(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    alias: Optional[str] = None
    executor: Optional[Executor] = None
    query: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

class Parameter(BaseModel):
    id: str
    name: str
    type: str
    defaultValue: Optional[Any] = None

class Artifact(BaseModel):
    id: str
    type: str
    title: Optional[str] = ""
    config: Optional[Dict[str, Any]] = None

class LayoutItem(BaseModel):
    id: str
    x: int = 0
    y: int = 0
    w: int = 1
    h: int = 1
    artifactId: Optional[str] = None

class Layout(BaseModel):
    items: List[LayoutItem] = []
    columns: Optional[int] = 1
    rows: Optional[int] = 1

class Report(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    dataSources: List[DataSource] = []
    parameters: List[Parameter] = []
    artifacts: List[Artifact] = []
    layout: Layout

    class Config:
        extra = "allow"  # 允许额外字段