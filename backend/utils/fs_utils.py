import os
import json
import multiprocessing
import aiofiles
from typing import List, Optional, Dict, Any
from pathlib import Path
from models.fs_models import FileSystemItem, FileSystemItemType

# 数据文件路径
DATA_DIR = Path(__file__).parent.parent.parent / "data"
FS_DATA_FILE = os.path.join(DATA_DIR, "fs_items.json")


# 设置实际文件存储的基础路径
FILE_STORAGE_PATH = os.path.join(DATA_DIR, "files")
FILE_DELETED_PATH = os.path.join(DATA_DIR, "files_deleted")
FILE_CACHE_PATH = os.path.join(DATA_DIR, "files_cache")
FILE_TOKEN_PATH = os.path.join(DATA_DIR, "tokens")

# 创建一个全局的文件系统数据锁
fs_data_lock = multiprocessing.Lock()


async def load_fs_data() -> List[FileSystemItem]:
    """
    异步线程安全地加载文件系统数据，确保即使发生异常也能释放锁

    Returns:
        List[FileSystemItem]: 文件系统项目列表
    """
    if not os.path.exists(FS_DATA_FILE):
        return []

    try:
        with fs_data_lock:
            async with aiofiles.open(FS_DATA_FILE, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)

        # 将字典列表转换为FileSystemItem对象列表
        return [FileSystemItem(**item) for item in data]
    except (json.JSONDecodeError, IOError) as e:
        print(f"加载文件系统数据时发生错误: {e}")
        return []


async def save_fs_data(items: List[FileSystemItem]):
    """
    异步线程安全地保存文件系统数据，确保即使发生异常也能释放锁

    Args:
        items (List[FileSystemItem]): 要保存的文件系统项目列表
    """
    try:
        os.makedirs(os.path.dirname(FS_DATA_FILE), exist_ok=True)
        with fs_data_lock:
            # 确保数据目录存在
            async with aiofiles.open(FS_DATA_FILE, "w", encoding="utf-8") as f:
                await f.write(json.dumps(
                    [item.dict() for item in items],
                    ensure_ascii=False,
                    indent=2
                ))
    except IOError as e:
        print(f"保存文件系统数据时发生错误: {e}")


# 辅助函数：根据ID查找项目


def find_item_by_id(items: List[FileSystemItem], id: str) -> Optional[FileSystemItem]:
    """
    在给定的项目列表中查找指定ID的项目

    Args:
        items (List[FileSystemItem]): 项目列表
        id (str): 要查找的项目ID

    Returns:
        Optional[FileSystemItem]: 找到的项目，未找到则返回None
    """
    for item in items:
        if item.id == id:
            return item
    return None

# 辅助函数：获取项目的所有子项


def get_children(items: List[FileSystemItem], parent_id: str) -> List[FileSystemItem]:
    """
    获取指定父ID的所有子项

    Args:
        items (List[FileSystemItem]): 项目列表
        parent_id (str): 父项目ID

    Returns:
        List[FileSystemItem]: 子项目列表
    """
    return [item for item in items if item.parentId == parent_id]

# 辅助函数：检查文件夹是否为空


def is_folder_empty(items: List[FileSystemItem], folder_id: str) -> bool:
    """
    检查指定文件夹是否为空

    Args:
        items (List[FileSystemItem]): 项目列表
        folder_id (str): 文件夹ID

    Returns:
        bool: 文件夹是否为空
    """
    return len(get_children(items, folder_id)) == 0

# 辅助函数：递归获取文件夹及其子项的所有ID


def get_folder_and_children_ids(items: List[FileSystemItem], folder_id: str) -> List[str]:
    """
    获取指定文件夹及其所有子项的ID列表

    Args:
        items (List[FileSystemItem]): 项目列表
        folder_id (str): 文件夹ID

    Returns:
        List[str]: 文件夹及其子项的ID列表
    """
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
    """
    获取指向特定文件的所有引用

    Args:
        items (List[FileSystemItem]): 项目列表
        file_id (str): 文件ID

    Returns:
        List[FileSystemItem]: 指向该文件的引用列表
    """
    return [item for item in items if item.type == FileSystemItemType.REFERENCE and item.referenceTo == file_id]

# 获取项目的实际文件路径


def get_item_path(item: FileSystemItem) -> str:
    """
    获取项目的实际文件路径

    Args:
        item (FileSystemItem): 文件系统项目

    Returns:
        str: 项目的文件路径
    """
    if item.type == FileSystemItemType.FOLDER:
        return os.path.join(FILE_STORAGE_PATH, item.id)
    elif item.type == FileSystemItemType.FILE:
        return os.path.join(FILE_STORAGE_PATH, item.id + ".data")
    else:
        return ""  # 引用类型没有实际文件
