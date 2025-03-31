import os
import json
from typing import Optional, Dict, Any
from utils.fs_utils import FILE_STORAGE_PATH

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