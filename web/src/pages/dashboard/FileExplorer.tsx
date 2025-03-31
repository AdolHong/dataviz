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
  Link,
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
  createReference,
} from '@/types/models/fileSystem';
import type { FileSystemItem } from '@/types/models/fileSystem';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

// 拖放类型定义
interface DragItem {
  id: string;
  name: string;
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
  const [isDuplicateDialogOpen, setIsDuplicateDialogOpen] = useState(false);
  const [isCreateReferenceDialogOpen, setIsCreateReferenceDialogOpen] =
    useState(false);

  // 新建和编辑表单状态
  const [newItemName, setNewItemName] = useState('');
  const [newItemParent, setNewItemParent] = useState<string | null>(null);
  const [newItemType, setNewItemType] = useState<FileSystemItemType>(
    FileSystemItemType.FOLDER
  );
  const [selectedItem, setSelectedItem] = useState<FileSystemItem | null>(null);
  const [duplicateItemName, setDuplicateItemName] = useState('');
  const [itemToDuplicate, setItemToDuplicate] = useState<FileSystemItem | null>(
    null
  );
  const [referenceItemName, setReferenceItemName] = useState('');
  const [fileToReference, setFileToReference] = useState<FileSystemItem | null>(
    null
  );

  // 在组件内添加一个新的 state 用于存储引用路径
  const [referencePaths, setReferencePaths] = useState<string[]>([]);

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

    // 如果是文件，检查引用并获取引用路径
    if (item.type === FileSystemItemType.FILE) {
      const references = items.filter(
        (ref) =>
          ref.type === FileSystemItemType.REFERENCE &&
          (ref as any).referenceTo === item.id
      );

      if (references.length > 0) {
        // 收集每个引用的路径
        const paths = references.map((ref) => {
          // 获取引用所在的文件夹路径
          let path = ref.name;
          let currentId = ref.parentId;

          while (currentId) {
            const parent = items.find((item) => item.id === currentId);
            if (!parent) break;

            path = `${parent.name}/${path}`;
            currentId = parent.parentId;
          }

          return path;
        });

        setReferencePaths(paths);
      } else {
        setReferencePaths([]);
      }
    } else {
      setReferencePaths([]);
    }

    setIsDeleteDialogOpen(true);
  };

  // 打开复制对话框
  const openDuplicateDialog = (item: FileSystemItem) => {
    setItemToDuplicate(item);
    setDuplicateItemName(`${item.name} - 副本`); // 默认新文件名
    setIsDuplicateDialogOpen(true);
  };

  // 打开创建引用对话框
  const openCreateReferenceDialog = (item: FileSystemItem) => {
    if (item.type !== FileSystemItemType.FILE) {
      toast.error('只能为文件创建引用');
      return;
    }

    setFileToReference(item);
    setReferenceItemName(`${item.name} 的引用`); // 默认引用名称
    setIsCreateReferenceDialogOpen(true);
  };

  // 创建新项目
  const handleCreateItem = () => {
    if (newItemName.trim() === '') return;

    // 检查同目录下是否有重名项目
    const existingItem = items.find(
      (item) => item.name === newItemName && item.parentId === newItemParent
    );
    if (existingItem) {
      toast.error('同目录下已存在同名文件或文件夹');
      return;
    }

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

    // 检查同目录下是否有重名项目
    const existingItem = items.find(
      (item) =>
        item.name === newItemName && item.parentId === selectedItem.parentId
    );
    if (existingItem) {
      toast.error('同目录下已存在同名文件或文件夹');
      return;
    }

    const updatedItems = renameItem(items, selectedItem.id, newItemName);
    onItemsChange(updatedItems);
    setIsRenameDialogOpen(false);
  };

  // 处理复制文件
  const handleDuplicateItem = () => {
    if (!itemToDuplicate || duplicateItemName.trim() === '') return;

    // 检查同目录下是否有重名项目
    const existingItem = items.find(
      (item) =>
        item.name === duplicateItemName &&
        item.parentId === itemToDuplicate.parentId
    );
    if (existingItem) {
      toast.error('同目录下已存在同名文件或文件夹');
      return;
    }

    let updatedItems: FileSystemItem[];

    // 如果是引用类型，则创建一个新的引用
    if (itemToDuplicate.type === FileSystemItemType.REFERENCE) {
      // 假设引用有一个指向原始文件的 referenceTo 属性
      const referencedFileId = (itemToDuplicate as any).referenceTo;
      updatedItems = createReference(
        items,
        duplicateItemName,
        referencedFileId,
        itemToDuplicate.parentId
      );
    } else {
      // 普通文件复制
      updatedItems = createFile(
        items,
        duplicateItemName,
        (itemToDuplicate as any).reportId || `report-${Date.now()}`,
        itemToDuplicate.parentId
      );
    }

    onItemsChange(updatedItems);
    setIsDuplicateDialogOpen(false);
  };

  // 处理创建引用
  const handleCreateReference = () => {
    if (!fileToReference || referenceItemName.trim() === '') return;

    // 检查同目录下是否有重名项目
    const existingItem = items.find(
      (item) =>
        item.name === referenceItemName &&
        item.parentId === fileToReference.parentId
    );
    if (existingItem) {
      toast.error('同目录下已存在同名文件或文件夹');
      return;
    }

    const updatedItems = createReference(
      items,
      referenceItemName,
      fileToReference.id,
      fileToReference.parentId
    );

    onItemsChange(updatedItems);
    setIsCreateReferenceDialogOpen(false);
  };

  // 删除项目
  const handleDeleteItem = () => {
    if (!selectedItem) return;

    // 如果是文件，检查是否有引用
    if (selectedItem.type === FileSystemItemType.FILE) {
      const references = items.filter(
        (item) =>
          item.type === FileSystemItemType.REFERENCE &&
          (item as any).referenceTo === selectedItem.id
      );

      if (references.length > 0) {
        setIsDeleteDialogOpen(false);

        // 使用自定义对话框显示警告
        toast.warning(
          `此文件有 ${references.length} 个引用，删除后所有引用也将失效。确定要删除吗？`,
          {
            duration: 5000,
            action: {
              label: '确认删除',
              onClick: () => {
                const updatedItems = deleteItem(items, selectedItem.id);
                onItemsChange(updatedItems);
              },
            },
          }
        );
        return;
      }
    }

    // 常规删除逻辑
    const updatedItems = deleteItem(items, selectedItem.id);
    onItemsChange(updatedItems);
    setIsDeleteDialogOpen(false);
  };

  // 拖拽开始
  const handleDragStart = (e: React.DragEvent, item: FileSystemItem) => {
    setDraggedItem({
      id: item.id,
      name: item.name,
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

    // 检查同目录下是否有重名项目
    const existingItem = items.find(
      (item) =>
        item.name === draggedItem.name && item.parentId === targetFolder.id
    );
    if (existingItem) {
      toast.error('同目录下已存在同名文件或文件夹，无法移动');
      return;
    }

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
    const isReference = item.type === FileSystemItemType.REFERENCE;
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
              <div className='w-5 h-5 flex items-center justify-center mr-1 flex-shrink-0'>
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
              <div className='mr-2 flex-shrink-0'>
                {isFolder ? (
                  <Folder size={18} className='text-blackAlpha.900' />
                ) : isReference ? (
                  <Link size={18} className='text-blue-500' />
                ) : (
                  <File size={18} className='text-muted-foreground' />
                )}
              </div>

              {/* 名称 - 改为自动省略太长的名称 */}
              <div className='flex-1 truncate text-sm' title={item.name}>
                {item.name}
              </div>
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

            {/* 文件专有菜单项 */}
            {item.type === FileSystemItemType.FILE && (
              <>
                <ContextMenuItem
                  onClick={() => openCreateReferenceDialog(item)}
                >
                  <Link className='mr-2 h-4 w-4' />
                  <span>创建引用</span>
                </ContextMenuItem>
              </>
            )}

            {/* 复制选项，对文件和引用都可用 */}
            {item.type !== FileSystemItemType.FOLDER && (
              <ContextMenuItem onClick={() => openDuplicateDialog(item)}>
                <File className='mr-2 h-4 w-4' />
                <span>
                  {item.type === FileSystemItemType.REFERENCE
                    ? '复制引用'
                    : '复制文件'}
                </span>
              </ContextMenuItem>
            )}
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

    // 对项目进行排序：先文件夹，再文件，最后引用
    const sortedChildren = [...children].sort((a, b) => {
      const typeOrder = {
        [FileSystemItemType.FOLDER]: 0,
        [FileSystemItemType.FILE]: 1,
        [FileSystemItemType.REFERENCE]: 2,
      };

      return (
        typeOrder[a.type] - typeOrder[b.type] || a.name.localeCompare(b.name)
      );
    });

    return sortedChildren.map(renderItem);
  };

  return (
    <div className='h-full flex flex-col'>
      {/* 添加根目录右键菜单 */}
      <ContextMenu>
        <ContextMenuTrigger className='flex-1 overflow-auto pr-1 min-w-0'>
          <div className='space-y-0.5'>
            {renderItems(null)}
            {/* 如果没有任何项目，添加一个提示 */}
            {items.length === 0 && (
              <div className='text-center text-muted-foreground py-4'>
                右键添加文件或文件夹
              </div>
            )}
          </div>
        </ContextMenuTrigger>
        <ContextMenuContent className='w-56'>
          <ContextMenuItem
            onClick={() => openNewItemDialog(null, FileSystemItemType.FOLDER)}
          >
            <Folder className='mr-2 h-4 w-4 text-gray-500' />
            <span>新建文件夹</span>
          </ContextMenuItem>
          <ContextMenuItem
            onClick={() => openNewItemDialog(null, FileSystemItemType.FILE)}
          >
            <File className='mr-2 h-4 w-4' />
            <span>新建文件</span>
          </ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>

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
              {selectedItem?.type === FileSystemItemType.FOLDER ? (
                '删除文件夹将同时删除其中的所有内容，此操作不可撤销。'
              ) : selectedItem?.type === FileSystemItemType.FILE &&
                referencePaths.length > 0 ? (
                <div className='space-y-2'>
                  <p>
                    此文件有 {referencePaths.length}{' '}
                    个引用，删除后这些引用将失效：
                  </p>
                  <div className='bg-muted p-2 rounded-md text-xs max-h-32 overflow-y-auto'>
                    {referencePaths.map((path, index) => (
                      <div
                        key={index}
                        className='pb-1 border-b border-border/50 last:border-0 last:pb-0 mb-1 last:mb-0'
                      >
                        {path}
                      </div>
                    ))}
                  </div>
                  <p className='text-destructive'>
                    确定要删除此文件吗？此操作不可撤销。
                  </p>
                </div>
              ) : (
                '确定要删除此文件吗？此操作不可撤销。'
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant='outline'
              onClick={() => setIsDeleteDialogOpen(false)}
            >
              取消
            </Button>
            <Button variant='destructive' onClick={handleDeleteItem}>
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 复制文件对话框 */}
      <Dialog
        open={isDuplicateDialogOpen}
        onOpenChange={setIsDuplicateDialogOpen}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>复制文件</DialogTitle>
            <DialogDescription>请输入新文件名</DialogDescription>
          </DialogHeader>
          <Input
            value={duplicateItemName}
            onChange={(e) => setDuplicateItemName(e.target.value)}
            placeholder='新文件名'
            autoFocus
          />
          <DialogFooter>
            <Button
              variant='outline'
              onClick={() => setIsDuplicateDialogOpen(false)}
            >
              取消
            </Button>
            <Button onClick={handleDuplicateItem}>确定</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 创建引用对话框 */}
      <Dialog
        open={isCreateReferenceDialogOpen}
        onOpenChange={setIsCreateReferenceDialogOpen}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>创建引用</DialogTitle>
            <DialogDescription>请输入引用名称</DialogDescription>
          </DialogHeader>
          <Input
            value={referenceItemName}
            onChange={(e) => setReferenceItemName(e.target.value)}
            placeholder='引用名称'
            autoFocus
          />
          <DialogFooter>
            <Button
              variant='outline'
              onClick={() => setIsCreateReferenceDialogOpen(false)}
            >
              取消
            </Button>
            <Button onClick={handleCreateReference}>创建</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
