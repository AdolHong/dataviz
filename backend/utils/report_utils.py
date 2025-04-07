import os
import json
import multiprocessing
from typing import Optional, Dict
from utils.fs_utils import FILE_STORAGE_PATH
from models.report_models import Report

# 使用字典管理文件锁
file_locks: Dict[str, multiprocessing.Lock] = {}


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


def get_report_content(file_id: str) -> Optional[Report]:
    """
    获取报表文件内容，使用文件锁确保线程安全

    Args:
        file_id (str): 文件标识符

    Returns:
        Optional[Report]: 报表内容，如果文件不存在或解析失败则返回 None
    """
    # 获取文件路径
    file_path = os.path.join(FILE_STORAGE_PATH, file_id + ".data")

    # 获取文件锁
    file_lock = get_file_lock(file_id)

    with file_lock:
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return Report(**json.load(f))
        except json.JSONDecodeError:
            # 如果文件为空或格式不正确，返回空对象
            return None


def save_report_content(file_id: str, content: Report):
    """
    保存报表文件内容，使用文件锁确保线程安全

    Args:
        file_id (str): 文件标识符
        content (Report): 报表内容
    """
    file_path = os.path.join(FILE_STORAGE_PATH, file_id + ".data")

    # 获取文件锁
    file_lock = get_file_lock(file_id)

    with file_lock:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(content.dict(), f, ensure_ascii=False, indent=2)


def delete_report_content(file_id: str) -> bool:
    """
    删除报表文件

    Args:
        file_id (str): 文件标识符

    Returns:
        bool: 删除是否成功
    """
    file_path = os.path.join(FILE_STORAGE_PATH, file_id + ".data")

    # 获取文件锁
    file_lock = get_file_lock(file_id)

    with file_lock:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                # 删除对应的文件锁
                if file_id in file_locks:
                    del file_locks[file_id]
                return True
            return False
        except Exception as e:
            print(f"删除报告文件时发生错误: {e}")
            return False
