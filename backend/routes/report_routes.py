from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime

from models.fs_models import FileSystemItem, FileSystemItemType
from models.report_models import Report
from utils.fs_utils import load_fs_data, save_fs_data, find_item_by_id
from utils.report_utils import get_report_content, save_report_content

router = APIRouter(tags=["reports"])

# API端点：获取报表数据
@router.get("/report/{file_id}", response_model=Report)
def get_report(file_id: str):
    items = load_fs_data()
    
    # 查找文件
    file_item = find_item_by_id(items, file_id)
    if not file_item or file_item.type not in( FileSystemItemType.FILE, FileSystemItemType.REFERENCE ):
        raise HTTPException(status_code=404, detail="报表文件不存在")

    # 获取报表文件ID(文件或引用)
    report_file_id = file_item.id if file_item.type == FileSystemItemType.FILE else file_item.referenceTo

    # 获取报表内容
    report_content = get_report_content(report_file_id)
    if not report_content:
        # 如果文件为空，初始化一个默认的报表结构
        default_report = Report(**{
            "id": file_id,
            "title": file_item.name,
            "description": "",
            "dataSources": [],
            "parameters": [],
            "artifacts": [],
            "layout": {"items": []},
            "createdAt": datetime.now().isoformat(),
            "updatedAt": datetime.now().isoformat(),
        })
        save_report_content(file_id, default_report)
        return default_report
    return report_content

# API端点：获取报表数据
@router.get("/report/by_report_id/{report_id}}", response_model=Report)
def get_report_by_report_id(report_id: str):
    items = load_fs_data()

    file_items = [item for item in items if item.type == FileSystemItemType.FILE]
    if len(file_items) == 0:
        raise HTTPException(status_code=404, detail="报表文件不存在")
    elif len(file_items) > 1:
        raise HTTPException(status_code=404, detail="报表文件存在多个")
    
    file_item = file_items[0]

    if file_item.reportId != report_id:
        raise HTTPException(status_code=404, detail="报表文件不存在")

    # 获取报表内容
    return get_report_content(file_item.id)



# API端点：更新报表数据
@router.post("/report/{file_id}", response_model=Report)
def update_report(file_id: str, report: Report):
    print("Received report data:", report.dict())
    
    items = load_fs_data()
    
    # 查找文件
    file_item = find_item_by_id(items, file_id)
    if not file_item or file_item.type != FileSystemItemType.FILE:
        raise HTTPException(status_code=404, detail="报表文件不存在")
    
    # 确保ID一致
    if report.id != file_id:
        report.id = file_id
    
    # 保存报表内容
    save_report_content(file_id, report)
    
    # 更新文件系统项目的更新时间
    for i, item in enumerate(items):
        if item.id == file_id:
            items[i].updatedAt = datetime.now().isoformat()
            break
    
    save_fs_data(items)
    
    return report

def update_report_title(file_id: str, title: str):
    report_content = get_report_content(file_id)
    if report_content:
        report_content.title = title
        save_report_content(file_id, report_content)


# API端点：创建一个新的报表文件
@router.post("/reports", response_model=Report)
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
    save_report_content(file_id, report)
    
    return report

# API端点：获取所有报表列表
@router.get("/reports", response_model=List[Dict[str, Any]])
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
                "title": report_content.title,
                "description": report_content.description,
                "updatedAt": item.updatedAt,
                "createdAt": item.createdAt
            })
    
    return result