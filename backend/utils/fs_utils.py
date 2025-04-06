import os
import json
from typing import List, Optional, Dict, Any
from pathlib import Path
from models.fs_models import FileSystemItem, FileSystemItemType

# 数据文件路径
DATA_DIR = Path(__file__).parent.parent.parent / "data"
FS_DATA_FILE = os.path.join(DATA_DIR, "fs_items.json")
TOKEN_FILE = os.path.join(DATA_DIR, "token.duckdb")

# 设置实际文件存储的基础路径
FILE_STORAGE_PATH = os.path.join(DATA_DIR, "files")
FILE_DELETED_PATH = os.path.join(DATA_DIR, "files_deleted")
FILE_CACHE_PATH = os.path.join(DATA_DIR, "files_cache")



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