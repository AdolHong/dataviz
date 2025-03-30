import { useState, useRef, useEffect } from 'react';
import * as React from 'react';
import {
  ChevronRight,
  ChevronDown,
  File,
  Folder,
  Plus,
  Pencil,
  Trash,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import {
  FileSystemItemType,
  getChildItems,
  createFolder,
  createFile,
  renameItem,
  moveItem,
  deleteItem,
} from '@/types/models/fileSystem';
import type { FileSystemItem } from '@/types/models/fileSystem';
import { cn } from '@/lib/utils';

// 拖放类型定义
interface DragItem {
  id: string;
  type: FileSystemItemType;
}

interface FileExplorerProps {
  items: FileSystemItem[];
  onItemsChange: (items: FileSystemItem[]) => void;
  onSelectItem?: (item: FileSystemItem) => void;
}

export function FileExplorer({
  items,
  onItemsChange,
  onSelectItem,
}: FileExplorerProps) {
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
    new Set()
  );
  const [draggedItem, setDraggedItem] = useState<DragItem | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [activeItem, setActiveItem] = useState<string | null>(null);

  // 对话框状态
  const [isNewItemDialogOpen, setIsNewItemDialogOpen] = useState(false);
  const [isRenameDialogOpen, setIsRenameDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);

  // 新建和编辑表单状态
  const [newItemName, setNewItemName] = useState('');
  const [newItemParent, setNewItemParent] = useState<string | null>(null);
  const [newItemType, setNewItemType] = useState<FileSystemItemType>(
    FileSystemItemType.FOLDER
  );
  const [selectedItem, setSelectedItem] = useState<FileSystemItem | null>(null);

  // 展开/折叠文件夹
  const toggleFolder = (folderId: string) => {
    const newExpandedFolders = new Set(expandedFolders);
    if (newExpandedFolders.has(folderId)) {
      newExpandedFolders.delete(folderId);
    } else {
      newExpandedFolders.add(folderId);
    }
    setExpandedFolders(newExpandedFolders);
  };

  // 处理项目点击
  const handleItemClick = (item: FileSystemItem) => {
    setActiveItem(item.id);

    if (item.type === FileSystemItemType.FOLDER) {
      toggleFolder(item.id);
    } else if (onSelectItem) {
      onSelectItem(item);
    }
  };

  // 打开新建项目对话框
  const openNewItemDialog = (
    parentId: string | null,
    type: FileSystemItemType
  ) => {
    setNewItemName('');
    setNewItemParent(parentId);
    setNewItemType(type);
    setIsNewItemDialogOpen(true);
  };

  // 打开重命名对话框
  const openRenameDialog = (item: FileSystemItem) => {
    setSelectedItem(item);
    setNewItemName(item.name);
    setIsRenameDialogOpen(true);
  };

  // 打开删除确认对话框
  const openDeleteDialog = (item: FileSystemItem) => {
    setSelectedItem(item);
    setIsDeleteDialogOpen(true);
  };

  // 创建新项目
  const handleCreateItem = () => {
    if (newItemName.trim() === '') return;

    let updatedItems: FileSystemItem[];

    if (newItemType === FileSystemItemType.FOLDER) {
      updatedItems = createFolder(items, newItemName, newItemParent);
    } else {
      // 为简单起见，这里创建文件时使用一个临时reportId
      updatedItems = createFile(
        items,
        newItemName,
        `report-${Date.now()}`,
        newItemParent
      );
    }

    onItemsChange(updatedItems);
    setIsNewItemDialogOpen(false);

    // 如果是在文件夹内创建，确保文件夹是展开的
    if (newItemParent) {
      setExpandedFolders((prev) => new Set([...prev, newItemParent]));
    }
  };

  // 重命名项目
  const handleRenameItem = () => {
    if (!selectedItem || newItemName.trim() === '') return;

    const updatedItems = renameItem(items, selectedItem.id, newItemName);
    onItemsChange(updatedItems);
    setIsRenameDialogOpen(false);
  };

  // 删除项目
  const handleDeleteItem = () => {
    if (!selectedItem) return;

    const updatedItems = deleteItem(items, selectedItem.id);
    onItemsChange(updatedItems);
    setIsDeleteDialogOpen(false);
  };

  // 拖拽开始
  const handleDragStart = (e: React.DragEvent, item: FileSystemItem) => {
    setDraggedItem({
      id: item.id,
      type: item.type,
    });
    // 设置拖拽效果和数据
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData(
      'application/json',
      JSON.stringify({
        id: item.id,
        type: item.type,
      })
    );
  };

  // 拖拽结束
  const handleDragEnd = () => {
    setDraggedItem(null);
    setDropTarget(null);
  };

  // 拖拽悬停
  const handleDragOver = (e: React.DragEvent, item: FileSystemItem) => {
    e.preventDefault();
    e.stopPropagation();

    // 只允许拖放到文件夹上
    if (item.type === FileSystemItemType.FOLDER) {
      setDropTarget(item.id);
      e.dataTransfer.dropEffect = 'move';
    } else {
      e.dataTransfer.dropEffect = 'none';
    }
  };

  // 离开拖拽区域
  const handleDragLeave = () => {
    setDropTarget(null);
  };

  // 放下
  const handleDrop = (e: React.DragEvent, targetFolder: FileSystemItem) => {
    e.preventDefault();
    e.stopPropagation();

    if (!draggedItem || targetFolder.type !== FileSystemItemType.FOLDER) return;

    // 防止拖放到自己内部
    if (draggedItem.id === targetFolder.id) return;

    // 移动项目
    const updatedItems = moveItem(items, draggedItem.id, targetFolder.id);
    onItemsChange(updatedItems);

    // 确保目标文件夹是展开的
    setExpandedFolders((prev) => new Set([...prev, targetFolder.id]));

    setDraggedItem(null);
    setDropTarget(null);
  };

  // 渲染单个项目
  const renderItem = (item: FileSystemItem) => {
    const isFolder = item.type === FileSystemItemType.FOLDER;
    const isExpanded = isFolder && expandedFolders.has(item.id);
    const isDragging = draggedItem?.id === item.id;
    const isDropTarget = dropTarget === item.id;
    const isActive = activeItem === item.id;

    return (
      <div key={item.id} className='select-none'>
        <ContextMenu>
          <ContextMenuTrigger>
            <div
              className={cn(
                'flex items-center px-2 py-1.5 rounded-md cursor-pointer transition-colors group',
                isDragging ? 'opacity-50' : '',
                isDropTarget
                  ? 'bg-blue-100 dark:bg-blue-900/40'
                  : isActive
                    ? 'bg-secondary'
                    : 'hover:bg-secondary/50'
              )}
              onClick={() => handleItemClick(item)}
              draggable
              onDragStart={(e) => handleDragStart(e, item)}
              onDragEnd={handleDragEnd}
              onDragOver={(e) => handleDragOver(e, item)}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, item)}
            >
              {/* 展开/折叠图标 */}
              <div className='w-5 h-5 flex items-center justify-center mr-1'>
                {isFolder && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleFolder(item.id);
                    }}
                    className='focus:outline-none'
                  >
                    {isExpanded ? (
                      <ChevronDown
                        size={16}
                        className='text-muted-foreground'
                      />
                    ) : (
                      <ChevronRight
                        size={16}
                        className='text-muted-foreground'
                      />
                    )}
                  </button>
                )}
              </div>

              {/* 图标 */}
              <div className='mr-2'>
                {isFolder ? (
                  <Folder
                    size={18}
                    className='text-blue-500 dark:text-blue-400'
                  />
                ) : (
                  <File size={18} className='text-muted-foreground' />
                )}
              </div>

              {/* 名称 */}
              <div className='flex-1 truncate text-sm'>{item.name}</div>
            </div>
          </ContextMenuTrigger>

          <ContextMenuContent className='w-56'>
            {isFolder && (
              <>
                <ContextMenuItem
                  onClick={() =>
                    openNewItemDialog(item.id, FileSystemItemType.FOLDER)
                  }
                >
                  <Plus className='mr-2 h-4 w-4' />
                  <span>新建文件夹</span>
                </ContextMenuItem>
                <ContextMenuItem
                  onClick={() =>
                    openNewItemDialog(item.id, FileSystemItemType.FILE)
                  }
                >
                  <File className='mr-2 h-4 w-4' />
                  <span>新建文件</span>
                </ContextMenuItem>
                <ContextMenuSeparator />
              </>
            )}
            <ContextMenuItem onClick={() => openRenameDialog(item)}>
              <Pencil className='mr-2 h-4 w-4' />
              <span>重命名</span>
            </ContextMenuItem>
            <ContextMenuItem onClick={() => openDeleteDialog(item)}>
              <Trash className='mr-2 h-4 w-4' />
              <span>删除</span>
            </ContextMenuItem>
          </ContextMenuContent>
        </ContextMenu>

        {/* 子项目 */}
        {isFolder && isExpanded && (
          <div className='pl-5 mt-0.5 border-l ml-2.5 border-border/50'>
            {renderItems(item.id)}
          </div>
        )}
      </div>
    );
  };

  // 渲染指定父项的所有子项
  const renderItems = (parentId: string | null) => {
    const children = getChildItems(items, parentId);

    // 先展示文件夹，再展示文件
    const folders = children.filter(
      (item) => item.type === FileSystemItemType.FOLDER
    );
    const files = children.filter(
      (item) => item.type === FileSystemItemType.FILE
    );

    return [...folders, ...files].map(renderItem);
  };

  return (
    <div className='h-full flex flex-col'>
      <div className='flex items-center justify-between mb-4 px-1'>
        <h2 className='text-lg font-medium'>文件浏览器</h2>
      </div>

      <div className='space-y-0.5 overflow-auto flex-1 pr-1'>
        {renderItems(null)}
      </div>

      {/* 新建项目对话框 */}
      <Dialog open={isNewItemDialogOpen} onOpenChange={setIsNewItemDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {newItemType === FileSystemItemType.FOLDER
                ? '新建文件夹'
                : '新建文件'}
            </DialogTitle>
            <DialogDescription>
              请输入
              {newItemType === FileSystemItemType.FOLDER ? '文件夹' : '文件'}
              名称
            </DialogDescription>
          </DialogHeader>
          <Input
            value={newItemName}
            onChange={(e) => setNewItemName(e.target.value)}
            placeholder={
              newItemType === FileSystemItemType.FOLDER
                ? '文件夹名称'
                : '文件名称'
            }
            autoFocus
          />
          <DialogFooter>
            <Button
              variant='outline'
              onClick={() => setIsNewItemDialogOpen(false)}
            >
              取消
            </Button>
            <Button onClick={handleCreateItem}>创建</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 重命名对话框 */}
      <Dialog open={isRenameDialogOpen} onOpenChange={setIsRenameDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重命名</DialogTitle>
            <DialogDescription>请输入新的名称</DialogDescription>
          </DialogHeader>
          <Input
            value={newItemName}
            onChange={(e) => setNewItemName(e.target.value)}
            placeholder='新名称'
            autoFocus
          />
          <DialogFooter>
            <Button
              variant='outline'
              onClick={() => setIsRenameDialogOpen(false)}
            >
              取消
            </Button>
            <Button onClick={handleRenameItem}>确定</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认对话框 */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              {selectedItem?.type === FileSystemItemType.FOLDER
                ? '删除文件夹将同时删除其中的所有内容，此操作不可撤销。'
                : '确定要删除此文件吗？此操作不可撤销。'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant='outline'
              onClick={() => setIsDeleteDialogOpen(false)}
            >
              取消
            </Button>
            <Button onClick={handleDeleteItem}>删除</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
