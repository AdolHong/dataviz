from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from enum import Enum

# 文件系统项目类型
class FileSystemItemType(str, Enum):
    FOLDER = "folder"
    FILE = "file"
    REFERENCE = "reference"

# 文件系统操作类型
class FileSystemOperation(str, Enum):
    # 创建
    CREATE_FILE = "CREATE_FILE"
    CREATE_FOLDER = "CREATE_FOLDER"
    CREATE_REFERENCE = "CREATE_REFERENCE"
    
    # 删除
    DELETE_FILE = "DELETE_FILE"
    DELETE_FOLDER = "DELETE_FOLDER"
    DELETE_REFERENCE = "DELETE_REFERENCE"
    
    # 重命名
    RENAME_FOLDER = "RENAME_FOLDER"
    RENAME_FILE = "RENAME_FILE"
    RENAME_REFERENCE = "RENAME_REFERENCE"
    
    # 移动
    MOVE_ITEM = "MOVE_ITEM"

# 文件系统项目模型
class FileSystemItem(BaseModel):
    id: str
    name: str
    type: FileSystemItemType
    parentId: Optional[str] = None
    createdAt: str
    updatedAt: str
    reportId: Optional[str] = None
    referenceTo: Optional[str] = None

# 文件系统差异模型
class FileSystemDiff(BaseModel):
    type: FileSystemOperation
    item: FileSystemItem
    oldItem: Optional[FileSystemItem] = None

# 批量操作请求模型
class BatchOperationRequest(BaseModel):
    operations: List[FileSystemDiff]