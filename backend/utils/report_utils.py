import os
import json
import multiprocessing
import aiofiles
from datetime import datetime
from typing import Optional, Dict
from utils.fs_utils import FILE_STORAGE_PATH, FILE_DELETED_PATH
from models.report_models import Report
import asyncio

# 使用字典管理文件锁
file_locks: Dict[str, multiprocessing.Lock] = {}

# 使用 asyncio 的锁
_file_locks = {}
_file_lock_create_lock = asyncio.Lock()


def get_file_lock(file_id: str) -> multiprocessing.Lock:
    """
    获取或创建特定文件的锁

    Args:
        file_id (str): 文件标识符

    Returns:
        multiprocessing.Lock: 文件对应的锁
    """
    if file_id not in file_locks:
        file_locks[file_id] = multiprocessing.Lock()
    return file_locks[file_id]


async def get_report_content(file_id: str) -> Optional[Report]:
    """
    异步获取报表文件内容

    Args:
        file_id (str): 文件标识符

    Returns:
        Optional[Report]: 报表内容，如果文件不存在或解析失败则返回 None
    """
    file_path = os.path.join(FILE_STORAGE_PATH, file_id + ".data")

    if not os.path.exists(file_path):
        return None

    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
            return Report(**json.loads(content))
    except (json.JSONDecodeError, IOError) as e:
        print(f"读取报告文件时发生错误: {e}")
        raise


async def save_report_content(file_id: str, content: Report):
    """
    异步保存报表文件内容，确保锁能正常释放

    Args:
        file_id (str): 文件标识符
        content (Report): 报表内容
    """
    file_path = os.path.join(FILE_STORAGE_PATH, file_id + ".data")

    # 获取文件锁
    file_lock = get_file_lock(file_id)

    try:
        with file_lock:
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(content.dict(), ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"保存报告文件时发生错误: {e}")
        raise Exception(f"保存报告文件时发生错误: {e}")


def delete_report_content(file_id: str) -> bool:
    """
    软删除报表文件，确保锁能正常释放

    Args:
        file_id (str): 文件标识符

    Returns:
        bool: 删除是否成功
    """
    file_path = os.path.join(FILE_STORAGE_PATH, file_id + ".data")

    if os.path.exists(file_path):
        return

    # 获取文件锁
    file_lock = get_file_lock(file_id)

    try:
        with file_lock:
            if os.path.exists(FILE_DELETED_PATH):
                # 创建删除目录（如果不存在）
                os.makedirs(FILE_DELETED_PATH, exist_ok=True)

            # 构建删除文件的新路径，包含时间戳确保唯一性
            deleted_file_path = os.path.join(
                FILE_DELETED_PATH,
                datetime.now().strftime("%Y%m%dT%H%M%S") + "__" + file_id + ".data"
            )

            # 移动文件而不是删除
            os.rename(file_path, deleted_file_path)

            # 删除对应的文件锁
            if file_id in file_locks:
                del file_locks[file_id]
    except Exception as e:
        print(f"软删除报告文件时发生错误: {e}")
        return False
