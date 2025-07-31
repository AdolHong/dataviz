from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
import os
import uuid
from datetime import datetime

from models.fs_models import (
    FileSystemItem,
    FileSystemItemType,
    FileSystemOperation,
    BatchOperationRequest
)
import json
from utils.fs_utils import (
    load_fs_data,
    save_fs_data,
    find_item_by_id,
    is_folder_empty,
    get_folder_and_children_ids,
    get_item_path,
)

from routes.report_routes import update_report_title
from routes.auth_routes import verify_token_dependency
from utils.report_utils import delete_report_content, get_report_content, save_report_content

router = APIRouter(tags=["file-system"])


# API端点：获取所有文件系统项目
@router.get("/fs/items", response_model=List[FileSystemItem])
async def get_fs_items(username: str = Depends(verify_token_dependency)):
    return await load_fs_data()

# API端点：创建文件


@router.post("/fs/operations/create-file", response_model=FileSystemItem)
async def create_file(item: FileSystemItem, username: str = Depends(verify_token_dependency)):
    items = await load_fs_data()

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
    default_report = {
        "id": item.id,
        "title": item.name,
        "description": "",
        "dataSources": [],
        "parameters": [],
        "artifacts": [],
        "layout": {"items": []},
        "createdAt": datetime.now().isoformat(),
        "updatedAt": datetime.now().isoformat(),
    }

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(default_report))  # 创建空json文件

    # 添加到列表并保存
    items.append(item)
    await save_fs_data(items)
    return item

# API端点：创建文件夹


@router.post("/fs/operations/create-folder", response_model=FileSystemItem)
async def create_folder(item: FileSystemItem, username: str = Depends(verify_token_dependency)):
    items = await load_fs_data()

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
    await save_fs_data(items)
    return item

# API端点：创建引用


@router.post("/fs/operations/create-reference", response_model=FileSystemItem)
async def create_reference(item: FileSystemItem, username: str = Depends(verify_token_dependency)):
    items = await load_fs_data()

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
    await save_fs_data(items)
    return item

# API端点：删除文件


@router.delete("/fs/operations/delete-file/{file_id}", response_model=Dict[str, bool])
async def delete_file(file_id: str, username: str = Depends(verify_token_dependency)):
    items = await load_fs_data()

    # 查找文件
    file_item = find_item_by_id(items, file_id)
    if not file_item or file_item.type != FileSystemItemType.FILE:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 软删除报告内容
    delete_report_content(file_id)

    # 删除文件记录
    items = [item for item in items if item.id != file_id]

    # 删除指向该文件的所有引用
    items = [item for item in items if item.type !=
             FileSystemItemType.REFERENCE or item.referenceTo != file_id]

    await save_fs_data(items)
    return {"success": True}

# API端点：删除文件夹


@router.delete("/fs/operations/delete-folder/{folder_id}", response_model=Dict[str, bool])
async def delete_folder(folder_id: str, recursive: bool = False, username: str = Depends(verify_token_dependency)):
    items = await load_fs_data()

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

        # 软删除文件
        for item_id in [item_id for item_id in ids_to_remove if 'file' in item_id]:
            # 只调用delete_report_content，不需要在这里调用delete_file
            delete_report_content(item_id)

        # 删除文件夹和文件记录
        items = [item for item in items if item.id not in ids_to_remove]

        # 删除指向已删除文件的所有引用
        items = [item for item in items if item.type !=
                 FileSystemItemType.REFERENCE or item.referenceTo not in ids_to_remove]
    else:
        # 只删除文件夹本身
        items = [item for item in items if item.id != folder_id]

    await save_fs_data(items)
    return {"success": True}

# API端点：删除引用


@router.delete("/fs/operations/delete-reference/{reference_id}", response_model=Dict[str, bool])
async def delete_reference(reference_id: str, username: str = Depends(verify_token_dependency)):
    items = await load_fs_data()

    # 查找引用
    ref_item = find_item_by_id(items, reference_id)
    if not ref_item or ref_item.type != FileSystemItemType.REFERENCE:
        raise HTTPException(status_code=404, detail="引用不存在")

    # 删除引用
    items = [item for item in items if item.id != reference_id]

    await save_fs_data(items)
    return {"success": True}

# API端点：重命名文件夹


@router.put("/fs/operations/rename-folder/{folder_id}", response_model=FileSystemItem)
async def rename_folder(folder_id: str, new_name: str, username: str = Depends(verify_token_dependency)):
    items = await load_fs_data()

    # 查找文件夹
    folder_idx = next((i for i, item in enumerate(
        items) if item.id == folder_id and item.type == FileSystemItemType.FOLDER), None)
    if folder_idx is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    # 更新名称
    items[folder_idx].name = new_name
    items[folder_idx].updatedAt = datetime.now().isoformat()

    await save_fs_data(items)
    return items[folder_idx]

# API端点：重命名文件


@router.put("/fs/operations/rename-file/{file_id}", response_model=FileSystemItem)
async def rename_file(file_id: str, new_name: str, username: str = Depends(verify_token_dependency)):
    items = await load_fs_data()

    # 查找文件
    file_idx = next((i for i, item in enumerate(items) if item.id ==
                    file_id and item.type == FileSystemItemType.FILE), None)
    if file_idx is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 更新名称
    items[file_idx].name = new_name
    items[file_idx].updatedAt = datetime.now().isoformat()

    # 更新report的文件名
    update_report_title(file_id, new_name)

    # 更新目录结构
    await save_fs_data(items)
    return items[file_idx]

# API端点：重命名引用


@router.put("/fs/operations/rename-reference/{reference_id}", response_model=FileSystemItem)
async def rename_reference(reference_id: str, new_name: str, username: str = Depends(verify_token_dependency)):
    items = await load_fs_data()

    # 查找引用
    ref_idx = next((i for i, item in enumerate(items) if item.id ==
                   reference_id and item.type == FileSystemItemType.REFERENCE), None)
    if ref_idx is None:
        raise HTTPException(status_code=404, detail="引用不存在")

    # 更新名称
    items[ref_idx].name = new_name
    items[ref_idx].updatedAt = datetime.now().isoformat()

    await save_fs_data(items)
    return items[ref_idx]

# API端点：移动项目


@router.put("/fs/operations/move-item/{item_id}", response_model=FileSystemItem)
async def move_item(item_id: str, new_parent_id: Optional[str] = None, username: str = Depends(verify_token_dependency)):
    items = await load_fs_data()

    # 查找项目
    item_idx = next((i for i, item in enumerate(
        items) if item.id == item_id), None)
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
                raise HTTPException(
                    status_code=400, detail="不能将文件夹移动到自己或其子文件夹中")

    # 更新父ID
    items[item_idx].parentId = new_parent_id
    items[item_idx].updatedAt = datetime.now().isoformat()

    await save_fs_data(items)
    return items[item_idx]

# API端点：复制文件


@router.post("/fs/operations/duplicate-file", response_model=FileSystemItem)
async def duplicate_file(source_file_id: str, new_name: str, parent_id: Optional[str] = None, username: str = Depends(verify_token_dependency)):
    items = await load_fs_data()

    # 查找源文件
    source_file = find_item_by_id(items, source_file_id)
    if not source_file or source_file.type != FileSystemItemType.FILE:
        raise HTTPException(status_code=404, detail="源文件不存在")

    # 检查父文件夹是否存在
    if parent_id:
        parent = find_item_by_id(items, parent_id)
        if not parent or parent.type != FileSystemItemType.FOLDER:
            raise HTTPException(status_code=400, detail="父文件夹不存在")

    # 检查同目录下是否有重名文件
    existing_item = next((item for item in items if item.name == new_name and item.parentId == parent_id), None)
    if existing_item:
        raise HTTPException(status_code=400, detail="同目录下已存在同名文件")

    # 创建新文件项（使用时间戳格式，与前端保持一致）
    import time
    timestamp = int(time.time() * 1000)  # 生成毫秒级时间戳
    new_file_id = f"file-{timestamp}"
    new_report_id = f"report-{timestamp}"
    now = datetime.now().isoformat()
    
    new_file = FileSystemItem(
        id=new_file_id,
        name=new_name,
        type=FileSystemItemType.FILE,
        parentId=parent_id,
        createdAt=now,
        updatedAt=now,
        reportId=new_report_id
    )

    try:
        # 读取源文件内容
        source_content = await get_report_content(source_file_id)
        if source_content:
            # 更新复制文件的基本信息
            source_content.id = new_report_id  # 使用新的报表ID
            source_content.title = new_name
            source_content.createdAt = now
            source_content.updatedAt = now
            
            # 保存到新文件（使用文件系统ID作为文件名）
            await save_report_content(new_file_id, source_content)
        else:
            # 如果源文件内容不存在，创建默认内容
            from models.report_models import Report, Layout
            
            default_report = Report(
                id=new_report_id,  # 使用新的报表ID
                title=new_name,
                description="",
                dataSources=[],
                parameters=[],
                artifacts=[],
                layout=Layout(items=[]),
                createdAt=now,
                updatedAt=now,
            )
            
            # 保存到新文件
            await save_report_content(new_file_id, default_report)

    except Exception as e:
        print(f"复制文件内容失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"复制文件内容失败: {str(e)}")

    # 添加到文件系统列表并保存
    items.append(new_file)
    await save_fs_data(items)
    
    return new_file

# API端点：批量处理操作


@router.post("/fs/batch", response_model=Dict[str, Any])
async def batch_operations(request: BatchOperationRequest, username: str = Depends(verify_token_dependency)):
    results = []

    for operation in request.operations:
        try:
            if operation.type == FileSystemOperation.CREATE_FILE:
                result = await create_file(operation.item, username)
            elif operation.type == FileSystemOperation.CREATE_FOLDER:
                result = await create_folder(operation.item, username)
            elif operation.type == FileSystemOperation.CREATE_REFERENCE:
                result = await create_reference(operation.item, username)
            elif operation.type == FileSystemOperation.DELETE_FILE:
                result = await delete_file(operation.item.id, username)
            elif operation.type == FileSystemOperation.DELETE_FOLDER:
                result = await delete_folder(
                    operation.item.id, recursive=True, username=username)
            elif operation.type == FileSystemOperation.DELETE_REFERENCE:
                result = await delete_reference(operation.item.id, username)
            elif operation.type == FileSystemOperation.RENAME_FOLDER:
                result = await rename_folder(
                    operation.item.id, operation.item.name, username)
            elif operation.type == FileSystemOperation.RENAME_FILE:
                result = await rename_file(
                    operation.item.id, operation.item.name, username)
            elif operation.type == FileSystemOperation.RENAME_REFERENCE:
                result = await rename_reference(
                    operation.item.id, operation.item.name, username)
            elif operation.type == FileSystemOperation.MOVE_ITEM:
                result = await move_item(
                    operation.item.id, operation.item.parentId, username)
            elif operation.type == FileSystemOperation.DUPLICATE_FILE:
                # 从oldItem获取源文件ID，从item获取新文件信息
                source_file_id = operation.oldItem.id if operation.oldItem else operation.item.id
                result = await duplicate_file(
                    source_file_id, operation.item.name, operation.item.parentId, username)
            else:
                raise HTTPException(
                    status_code=400, detail=f"不支持的操作类型: {operation.type}")

            results.append({"success": True, "result": result})
        except HTTPException as e:
            results.append({"success": False, "error": e.detail})

    return {"results": results}
