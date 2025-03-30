// 定义文件系统中的项目类型：文件夹或文件
export enum FileSystemItemType {
  FOLDER = 'folder',
  FILE = 'file',
}

// 文件系统项的基础接口
export interface FileSystemItemBase {
  id: string;
  name: string;
  type: FileSystemItemType;
  parentId: string | null; // null表示根级项目
  createdAt: string;
  updatedAt: string;
}

// 文件特有属性
export interface FileItem extends FileSystemItemBase {
  type: FileSystemItemType.FILE;
  reportId: string; // 关联的报表ID
}

// 文件夹特有属性
export interface FolderItem extends FileSystemItemBase {
  type: FileSystemItemType.FOLDER;
}

// 统一文件系统项类型
export type FileSystemItem = FileItem | FolderItem;

// 整个文件系统的接口
export interface FileSystem {
  items: FileSystemItem[];
}

// 辅助函数：获取子项目
export const getChildItems = (
  items: FileSystemItem[],
  parentId: string | null
): FileSystemItem[] => {
  return items.filter((item) => item.parentId === parentId);
};

// 辅助函数：获取文件夹子项
export const getFolderChildren = (
  items: FileSystemItem[],
  folderId: string
): FileSystemItem[] => {
  return items.filter((item) => item.parentId === folderId);
};

// 辅助函数：根据ID查找项目
export const findItemById = (
  items: FileSystemItem[],
  id: string
): FileSystemItem | undefined => {
  return items.find((item) => item.id === id);
};

// 辅助函数：获取项目路径
export const getItemPath = (
  items: FileSystemItem[],
  itemId: string
): FileSystemItem[] => {
  const path: FileSystemItem[] = [];
  let currentId: string | null = itemId;

  while (currentId) {
    const item = findItemById(items, currentId);
    if (!item) break;

    path.unshift(item);
    currentId = item.parentId;
  }

  return path;
};

// 辅助函数：创建新文件夹
export const createFolder = (
  items: FileSystemItem[],
  name: string,
  parentId: string | null = null
): FileSystemItem[] => {
  const newFolder: FolderItem = {
    id: `folder-${Date.now()}`,
    name,
    type: FileSystemItemType.FOLDER,
    parentId,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };

  return [...items, newFolder];
};

// 辅助函数：创建新文件
export const createFile = (
  items: FileSystemItem[],
  name: string,
  reportId: string,
  parentId: string | null = null
): FileSystemItem[] => {
  const newFile: FileItem = {
    id: `file-${Date.now()}`,
    name,
    type: FileSystemItemType.FILE,
    parentId,
    reportId,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };

  return [...items, newFile];
};

// 辅助函数：重命名项目
export const renameItem = (
  items: FileSystemItem[],
  itemId: string,
  newName: string
): FileSystemItem[] => {
  return items.map((item) =>
    item.id === itemId
      ? { ...item, name: newName, updatedAt: new Date().toISOString() }
      : item
  );
};

// 辅助函数：移动项目
export const moveItem = (
  items: FileSystemItem[],
  itemId: string,
  newParentId: string | null
): FileSystemItem[] => {
  return items.map((item) =>
    item.id === itemId
      ? { ...item, parentId: newParentId, updatedAt: new Date().toISOString() }
      : item
  );
};

// 辅助函数：删除项目及其所有子项
export const deleteItem = (
  items: FileSystemItem[],
  itemId: string
): FileSystemItem[] => {
  const itemToDelete = findItemById(items, itemId);
  if (!itemToDelete) return items;

  // 如果是文件夹，递归删除所有子项
  if (itemToDelete.type === FileSystemItemType.FOLDER) {
    const childrenIds = getChildItems(items, itemId).map((child) => child.id);
    let result = [...items];

    for (const childId of childrenIds) {
      result = deleteItem(result, childId);
    }

    return result.filter((item) => item.id !== itemId);
  }

  // 如果是文件，直接删除
  return items.filter((item) => item.id !== itemId);
};
