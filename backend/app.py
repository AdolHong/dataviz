from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Union, Dict, Any
from enum import Enum
import os
import json
import shutil
from datetime import datetime
import uuid

app = FastAPI()

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React 开发服务器
        "http://127.0.0.1:3000",
        "https://localhost:3000",
        "https://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有请求头
)

# 数据文件路径
DATA_DIR = "data"
FS_DATA_FILE = os.path.join(DATA_DIR, "fs_items.json")

# 设置实际文件存储的基础路径
FILE_STORAGE_PATH = os.path.join(DATA_DIR, "files")
os.makedirs(FILE_STORAGE_PATH, exist_ok=True)

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

# 报表相关的模型
class DataSource(BaseModel):
    id: str
    # 添加其他必要字段
    name: str
    query: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

class Parameter(BaseModel):
    id: str
    name: str
    type: str
    defaultValue: Optional[Any] = None
    # 添加其他必要字段

class Artifact(BaseModel):
    id: str
    type: str
    config: Optional[Dict[str, Any]] = None
    # 添加其他必要字段

class LayoutItem(BaseModel):
    id: str
    x: int
    y: int
    w: int
    h: int
    artifactId: str

class Layout(BaseModel):
    items: List[LayoutItem]

class Report(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    dataSources: List[DataSource] = []
    parameters: List[Parameter] = []
    artifacts: List[Artifact] = []
    layout: Layout

# 文件系统差异模型
class FileSystemDiff(BaseModel):
    type: FileSystemOperation
    item: FileSystemItem
    oldItem: Optional[FileSystemItem] = None

# 批量操作请求模型
class BatchOperationRequest(BaseModel):
    operations: List[FileSystemDiff]

# 辅助函数：加载文件系统数据
def load_fs_data() -> List[FileSystemItem]:
    if not os.path.exists(FS_DATA_FILE):
        return []
    
    with open(FS_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 将字典列表转换为FileSystemItem对象列表
    return [FileSystemItem(**item) for item in data]

# 辅助函数：保存文件系统数据
def save_fs_data(items: List[FileSystemItem]):
    with open(FS_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump([item.dict() for item in items], f, ensure_ascii=False, indent=2)

# 辅助函数：获取报表文件的内容
def get_report_content(file_id: str) -> Optional[Dict[str, Any]]:
    # 获取文件路径
    file_path = os.path.join(FILE_STORAGE_PATH, file_id + ".data")
    if not os.path.exists(file_path):
        return None
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # 如果文件为空或格式不正确，返回空对象
        return {}

# 辅助函数：保存报表文件内容
def save_report_content(file_id: str, content: Dict[str, Any]):
    file_path = os.path.join(FILE_STORAGE_PATH, file_id + ".data")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

# 辅助函数：根据ID查找项目
def find_item_by_id(items: List[FileSystemItem], id: str) -> Optional[FileSystemItem]:
    for item in items:
        if item.id == id:
            return item
    return None

# 辅助函数：获取项目的所有子项
def get_children(items: List[FileSystemItem], parent_id: str) -> List[FileSystemItem]:
    return [item for item in items if item.parentId == parent_id]

# 辅助函数：检查文件夹是否为空
def is_folder_empty(items: List[FileSystemItem], folder_id: str) -> bool:
    return len(get_children(items, folder_id)) == 0

# 辅助函数：递归获取文件夹及其子项的所有ID
def get_folder_and_children_ids(items: List[FileSystemItem], folder_id: str) -> List[str]:
    result = [folder_id]
    children = get_children(items, folder_id)
    
    for child in children:
        if child.type == FileSystemItemType.FOLDER:
            result.extend(get_folder_and_children_ids(items, child.id))
        else:
            result.append(child.id)
    
    return result

# 辅助函数：获取引用该文件的所有引用
def get_references_to_file(items: List[FileSystemItem], file_id: str) -> List[FileSystemItem]:
    return [item for item in items if item.type == FileSystemItemType.REFERENCE and item.referenceTo == file_id]

# 获取项目的实际文件路径
def get_item_path(item: FileSystemItem) -> str:
    if item.type == FileSystemItemType.FOLDER:
        return os.path.join(FILE_STORAGE_PATH, item.id)
    elif item.type == FileSystemItemType.FILE:
        return os.path.join(FILE_STORAGE_PATH, item.id + ".data")
    else:
        return ""  # 引用类型没有实际文件

# API端点：获取所有文件系统项目
@app.get("/api/fs/items", response_model=List[FileSystemItem])
def get_fs_items():
    return load_fs_data()

# API端点：获取报表数据
@app.get("/api/report/{file_id}", response_model=Report)
def get_report(file_id: str):
    items = load_fs_data()
    
    # 查找文件
    file_item = find_item_by_id(items, file_id)
    if not file_item or file_item.type != FileSystemItemType.FILE:
        raise HTTPException(status_code=404, detail="报表文件不存在")
    
    # 获取报表内容
    report_content = get_report_content(file_id)
    if not report_content:
        # 如果文件为空，初始化一个默认的报表结构
        default_report = {
            "id": file_id,
            "title": file_item.name,
            "description": "",
            "dataSources": [],
            "parameters": [],
            "artifacts": [],
            "layout": {"items": []}
        }
        save_report_content(file_id, default_report)
        return Report(**default_report)
    return Report(**report_content)

# API端点：更新报表数据
@app.post("/api/report/{file_id}", response_model=Report)
def update_report(file_id: str, report: Report):
    print("Received report data:", report.dict())
    
    items = load_fs_data()

    print("report:", report)
    
    # 查找文件
    file_item = find_item_by_id(items, file_id)
    if not file_item or file_item.type != FileSystemItemType.FILE:
        raise HTTPException(status_code=404, detail="报表文件不存在")
    
    # 确保ID一致
    if report.id != file_id:
        report.id = file_id
    
    # 保存报表内容
    save_report_content(file_id, report.dict())
    
    # 更新文件系统项目的更新时间
    for i, item in enumerate(items):
        if item.id == file_id:
            items[i].updatedAt = datetime.now().isoformat()
            break
    
    save_fs_data(items)
    
    return report

# API端点：创建一个新的报表文件
@app.post("/api/reports", response_model=Report)
def create_report(report: Report, parent_id: Optional[str] = None):
    items = load_fs_data()
    
    # 检查父文件夹是否存在
    if parent_id:
        parent = find_item_by_id(items, parent_id)
        if not parent or parent.type != FileSystemItemType.FOLDER:
            raise HTTPException(status_code=400, detail="父文件夹不存在")
    
    # 创建文件系统项目
    file_id = f"file-{uuid.uuid4()}"
    now = datetime.now().isoformat()
    
    new_item = FileSystemItem(
        id=file_id,
        name=report.title,
        type=FileSystemItemType.FILE,
        parentId=parent_id,
        createdAt=now,
        updatedAt=now,
        reportId=report.id
    )
    
    # 确保报表ID与文件ID一致
    report.id = file_id
    
    # 保存文件系统项目
    items.append(new_item)
    save_fs_data(items)
    
    # 保存报表内容
    save_report_content(file_id, report.dict())
    
    return report

# API端点：获取所有报表列表
@app.get("/api/reports", response_model=List[Dict[str, Any]])
def list_reports():
    items = load_fs_data()
    
    # 找出所有文件类型的项目
    file_items = [item for item in items if item.type == FileSystemItemType.FILE]
    
    result = []
    for item in file_items:
        # 获取报表内容
        report_content = get_report_content(item.id)
        if report_content:
            result.append({
                "id": item.id,
                "title": report_content.get("title", item.name),
                "description": report_content.get("description", ""),
                "updatedAt": item.updatedAt,
                "createdAt": item.createdAt
            })
    
    return result

# API端点：创建文件
@app.post("/api/fs/operations/create-file", response_model=FileSystemItem)
def create_file(item: FileSystemItem):
    items = load_fs_data()
    
    # 检查父文件夹是否存在
    if item.parentId:
        parent = find_item_by_id(items, item.parentId)
        if not parent or parent.type != FileSystemItemType.FOLDER:
            raise HTTPException(status_code=400, detail="父文件夹不存在")
    
    # 确保ID和时间戳
    if not item.id:
        item.id = f"file-{uuid.uuid4()}"
    now = datetime.now().isoformat()
    item.createdAt = now
    item.updatedAt = now
    
    # 创建实际文件
    file_path = get_item_path(item)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("{}")  # 创建空json文件
    
    # 添加到列表并保存
    items.append(item)
    save_fs_data(items)
    return item

# API端点：创建文件夹
@app.post("/api/fs/operations/create-folder", response_model=FileSystemItem)
def create_folder(item: FileSystemItem):
    items = load_fs_data()
    
    # 检查父文件夹是否存在
    if item.parentId:
        parent = find_item_by_id(items, item.parentId)
        if not parent or parent.type != FileSystemItemType.FOLDER:
            raise HTTPException(status_code=400, detail="父文件夹不存在")
    
    # 确保ID和时间戳
    if not item.id:
        item.id = f"folder-{uuid.uuid4()}"
    now = datetime.now().isoformat()
    item.createdAt = now
    item.updatedAt = now
        
    # 添加到列表并保存
    items.append(item)
    save_fs_data(items)
    return item

# API端点：创建引用
@app.post("/api/fs/operations/create-reference", response_model=FileSystemItem)
def create_reference(item: FileSystemItem):
    items = load_fs_data()
    
    # 检查引用的原始文件是否存在
    if not item.referenceTo:
        raise HTTPException(status_code=400, detail="未指定引用目标")
    
    original_file = find_item_by_id(items, item.referenceTo)
    if not original_file or original_file.type != FileSystemItemType.FILE:
        raise HTTPException(status_code=400, detail="引用的文件不存在")
    
    # 检查父文件夹是否存在
    if item.parentId:
        parent = find_item_by_id(items, item.parentId)
        if not parent or parent.type != FileSystemItemType.FOLDER:
            raise HTTPException(status_code=400, detail="父文件夹不存在")
    
    # 确保ID和时间戳
    if not item.id:
        item.id = f"ref-{uuid.uuid4()}"
    now = datetime.now().isoformat()
    item.createdAt = now
    item.updatedAt = now
    
    # 添加到列表并保存
    items.append(item)
    save_fs_data(items)
    return item

# API端点：删除文件
@app.delete("/api/fs/operations/delete-file/{file_id}", response_model=Dict[str, bool])
def delete_file(file_id: str):
    items = load_fs_data()
    
    # 查找文件
    file_item = find_item_by_id(items, file_id)
    if not file_item or file_item.type != FileSystemItemType.FILE:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 删除实际文件
    file_path = get_item_path(file_item)
    if os.path.exists(file_path):
        os.remove(file_path)
    
    # 删除文件记录
    items = [item for item in items if item.id != file_id]
    
    # 删除指向该文件的所有引用
    items = [item for item in items if item.type != FileSystemItemType.REFERENCE or item.referenceTo != file_id]
    
    save_fs_data(items)
    return {"success": True}

# API端点：删除文件夹
@app.delete("/api/fs/operations/delete-folder/{folder_id}", response_model=Dict[str, bool])
def delete_folder(folder_id: str, recursive: bool = False):
    items = load_fs_data()
    
    # 查找文件夹
    folder_item = find_item_by_id(items, folder_id)
    if not folder_item or folder_item.type != FileSystemItemType.FOLDER:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    
    # 检查文件夹是否为空
    if not recursive and not is_folder_empty(items, folder_id):
        raise HTTPException(status_code=400, detail="文件夹不为空，无法删除")
    
    # 递归删除
    if recursive:
        ids_to_remove = get_folder_and_children_ids(items, folder_id)
        items = [item for item in items if item.id not in ids_to_remove]
        print("ids_to_remove", ids_to_remove)
        print("items", items)
        
        # 删除指向已删除文件的所有引用
        items = [item for item in items if item.type != FileSystemItemType.REFERENCE or item.referenceTo not in ids_to_remove]

        # 实际删除文件
        for item_id in [item_id for item_id in ids_to_remove if 'file' in item_id]:
            delete_file(item_id)

    else:
        # 只删除文件夹本身
        items = [item for item in items if item.id != folder_id]
    
    save_fs_data(items)
    return {"success": True}

# API端点：删除引用
@app.delete("/api/fs/operations/delete-reference/{reference_id}", response_model=Dict[str, bool])
def delete_reference(reference_id: str):
    items = load_fs_data()
    
    # 查找引用
    ref_item = find_item_by_id(items, reference_id)
    if not ref_item or ref_item.type != FileSystemItemType.REFERENCE:
        raise HTTPException(status_code=404, detail="引用不存在")
    
    # 删除引用
    items = [item for item in items if item.id != reference_id]
    
    save_fs_data(items)
    return {"success": True}

# API端点：重命名文件夹
@app.put("/api/fs/operations/rename-folder/{folder_id}", response_model=FileSystemItem)
def rename_folder(folder_id: str, new_name: str):
    items = load_fs_data()
    
    # 查找文件夹
    folder_idx = next((i for i, item in enumerate(items) if item.id == folder_id and item.type == FileSystemItemType.FOLDER), None)
    if folder_idx is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    
    # 更新名称
    items[folder_idx].name = new_name
    items[folder_idx].updatedAt = datetime.now().isoformat()
    
    save_fs_data(items)
    return items[folder_idx]

# API端点：重命名文件
@app.put("/api/fs/operations/rename-file/{file_id}", response_model=FileSystemItem)
def rename_file(file_id: str, new_name: str):
    items = load_fs_data()
    
    # 查找文件
    file_idx = next((i for i, item in enumerate(items) if item.id == file_id and item.type == FileSystemItemType.FILE), None)
    if file_idx is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 更新名称
    items[file_idx].name = new_name
    items[file_idx].updatedAt = datetime.now().isoformat()
    
    save_fs_data(items)
    return items[file_idx]

# API端点：重命名引用
@app.put("/api/fs/operations/rename-reference/{reference_id}", response_model=FileSystemItem)
def rename_reference(reference_id: str, new_name: str):
    items = load_fs_data()
    
    # 查找引用
    ref_idx = next((i for i, item in enumerate(items) if item.id == reference_id and item.type == FileSystemItemType.REFERENCE), None)
    if ref_idx is None:
        raise HTTPException(status_code=404, detail="引用不存在")
    
    # 更新名称
    items[ref_idx].name = new_name
    items[ref_idx].updatedAt = datetime.now().isoformat()
    
    save_fs_data(items)
    return items[ref_idx]

# API端点：移动项目
@app.put("/api/fs/operations/move-item/{item_id}", response_model=FileSystemItem)
def move_item(item_id: str, new_parent_id: Optional[str] = None):
    items = load_fs_data()
    
    # 查找项目
    item_idx = next((i for i, item in enumerate(items) if item.id == item_id), None)
    if item_idx is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 检查新父文件夹是否存在
    if new_parent_id:
        parent = find_item_by_id(items, new_parent_id)
        if not parent or parent.type != FileSystemItemType.FOLDER:
            raise HTTPException(status_code=400, detail="目标文件夹不存在")
        
        # 不能将文件夹移动到自己或其子文件夹中
        if items[item_idx].type == FileSystemItemType.FOLDER:
            child_ids = get_folder_and_children_ids(items, item_id)
            if new_parent_id in child_ids:
                raise HTTPException(status_code=400, detail="不能将文件夹移动到自己或其子文件夹中")
    
    # 更新父ID
    items[item_idx].parentId = new_parent_id
    items[item_idx].updatedAt = datetime.now().isoformat()
    
    save_fs_data(items)
    return items[item_idx]

# API端点：批量处理操作
@app.post("/api/fs/batch", response_model=Dict[str, Any])
def batch_operations(request: BatchOperationRequest):
    results = []
    
    
    print("多少操作", len(request.operations))
    print("操作", request.operations)


    for operation in request.operations:
        try:
            if operation.type == FileSystemOperation.CREATE_FILE:
                result = create_file(operation.item)
            elif operation.type == FileSystemOperation.CREATE_FOLDER:
                result = create_folder(operation.item)
            elif operation.type == FileSystemOperation.CREATE_REFERENCE:
                result = create_reference(operation.item)
            elif operation.type == FileSystemOperation.DELETE_FILE:
                result = delete_file(operation.item.id)
            elif operation.type == FileSystemOperation.DELETE_FOLDER:
                result = delete_folder(operation.item.id, recursive=True)
            elif operation.type == FileSystemOperation.DELETE_REFERENCE:
                result = delete_reference(operation.item.id)
            elif operation.type == FileSystemOperation.RENAME_FOLDER:
                result = rename_folder(operation.item.id, operation.item.name)
            elif operation.type == FileSystemOperation.RENAME_FILE:
                result = rename_file(operation.item.id, operation.item.name)
            elif operation.type == FileSystemOperation.RENAME_REFERENCE:
                result = rename_reference(operation.item.id, operation.item.name)
            elif operation.type == FileSystemOperation.MOVE_ITEM:
                result = move_item(operation.item.id, operation.item.parentId)
            else:
                raise HTTPException(status_code=400, detail=f"不支持的操作类型: {operation.type}")
            
            results.append({"success": True, "result": result})
        except HTTPException as e:
            results.append({"success": False, "error": e.detail})
    
    return {"results": results}

# 启动初始化：如果数据文件不存在，创建一个空的文件系统
@app.on_event("startup")
def startup_event():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    
    if not os.path.exists(FS_DATA_FILE):
        save_fs_data([])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)