import { axiosInstance } from '@/lib/axios';
import { FileSystemItemType } from '@/types/models/fileSystem';
import type { FileSystemItem } from '@/types/models/fileSystem';

enum FileSystemOperation {
  // 创建
  CREATE_FILE = 'CREATE_FILE',
  CREATE_FOLDER = 'CREATE_FOLDER',
  CREATE_REFERENCE = 'CREATE_REFERENCE',

  // 删除
  DELETE_FILE = 'DELETE_FILE',
  DELETE_FOLDER = 'DELETE_FOLDER',
  DELETE_REFERENCE = 'DELETE_REFERENCE',

  // 重命名
  RENAME_FOLDER = 'RENAME_FOLDER',
  RENAME_FILE = 'RENAME_FILE',
  RENAME_REFERENCE = 'RENAME_REFERENCE',

  // 移动
  MOVE_ITEM = 'MOVE_ITEM',
}

interface FileSystemDiff {
  type: FileSystemOperation;
  item: FileSystemItem;
  oldItem?: FileSystemItem;
}

// 检查两个文件系统项目列表之间的差异
const checkItemsDiff = (
  oldItems: FileSystemItem[],
  newItems: FileSystemItem[]
): FileSystemDiff[] => {
  const oldItemsMap = new Map(oldItems.map((item) => [item.id, item]));
  const newItemsMap = new Map(newItems.map((item) => [item.id, item]));
  const diff: FileSystemDiff[] = [];

  // 检查新增项目
  for (const newItem of newItems) {
    const oldItem = oldItemsMap.get(newItem.id);

    if (!oldItem) {
      // 新建文件
      if (newItem.type === FileSystemItemType.FILE) {
        diff.push({
          type: FileSystemOperation.CREATE_FILE,
          item: newItem,
        });
      }
      // 新建文件夹
      else if (newItem.type === FileSystemItemType.FOLDER) {
        diff.push({
          type: FileSystemOperation.CREATE_FOLDER,
          item: newItem,
        });
      }
      // 新建引用
      else if (newItem.type === FileSystemItemType.REFERENCE) {
        diff.push({
          type: FileSystemOperation.CREATE_REFERENCE,
          item: newItem,
        });
      }
      continue;
    }

    // 重命名文件夹
    if (
      oldItem.type === FileSystemItemType.FOLDER &&
      oldItem.name !== newItem.name
    ) {
      diff.push({
        type: FileSystemOperation.RENAME_FOLDER,
        item: newItem,
        oldItem: oldItem,
      });
    }

    // 重命名文件
    if (
      oldItem.type === FileSystemItemType.FILE &&
      oldItem.name !== newItem.name
    ) {
      diff.push({
        type: FileSystemOperation.RENAME_FILE,
        item: newItem,
        oldItem: oldItem,
      });
    }

    // 移动文件或文件夹
    if (oldItem.parentId !== newItem.parentId) {
      diff.push({
        type: FileSystemOperation.MOVE_ITEM,
        item: newItem,
        oldItem: oldItem,
      });
    }

    // 重命名引用
    if (
      oldItem.type === FileSystemItemType.REFERENCE &&
      oldItem.name !== newItem.name
    ) {
      diff.push({
        type: FileSystemOperation.RENAME_REFERENCE,
        item: newItem,
        oldItem: oldItem,
      });
    }
  }

  // 检查删除项目
  for (const oldItem of oldItems) {
    const newItem = newItemsMap.get(oldItem.id);

    if (!newItem) {
      // 删除文件
      if (oldItem.type === FileSystemItemType.FILE) {
        diff.push({
          type: FileSystemOperation.DELETE_FILE,
          item: oldItem,
        });
      }
      // 删除文件夹
      else if (oldItem.type === FileSystemItemType.FOLDER) {
        diff.push({
          type: FileSystemOperation.DELETE_FOLDER,
          item: oldItem,
        });
      }
      // 删除引用
      else if (oldItem.type === FileSystemItemType.REFERENCE) {
        diff.push({
          type: FileSystemOperation.DELETE_REFERENCE,
          item: oldItem,
        });
      }
    }
  }

  return diff;
};

export const fsApi = {
  // 获取所有文件系统项目
  async getAllItems(): Promise<FileSystemItem[]> {
    const response = await axiosInstance.get<{ data: FileSystemItem[] }>(
      '/fs/items'
    );
    return response.data.data;
  },

  // 创建文件
  async createFile(item: FileSystemItem): Promise<FileSystemItem> {
    const response = await axiosInstance.post(
      '/fs/operations/create-file',
      item
    );
    return response.data;
  },

  // 创建文件夹
  async createFolder(item: FileSystemItem): Promise<FileSystemItem> {
    const response = await axiosInstance.post(
      '/fs/operations/create-folder',
      item
    );
    return response.data;
  },

  // 创建引用
  async createReference(item: FileSystemItem): Promise<FileSystemItem> {
    const response = await axiosInstance.post(
      '/fs/operations/create-reference',
      item
    );
    return response.data;
  },

  // 删除文件
  async deleteFile(fileId: string): Promise<boolean> {
    const response = await axiosInstance.delete(
      `/fs/operations/delete-file/${fileId}`
    );
    return response.data.success;
  },

  // 删除文件夹
  async deleteFolder(
    folderId: string,
    recursive: boolean = false
  ): Promise<boolean> {
    const response = await axiosInstance.delete(
      `/fs/operations/delete-folder/${folderId}`,
      {
        params: { recursive },
      }
    );
    return response.data.success;
  },

  // 删除引用
  async deleteReference(referenceId: string): Promise<boolean> {
    const response = await axiosInstance.delete(
      `/fs/operations/delete-reference/${referenceId}`
    );
    return response.data.success;
  },

  // 重命名文件夹
  async renameFolder(
    folderId: string,
    newName: string
  ): Promise<FileSystemItem> {
    const response = await axiosInstance.put(
      `/fs/operations/rename-folder/${folderId}`,
      null,
      {
        params: { new_name: newName },
      }
    );
    return response.data;
  },

  // 重命名文件
  async renameFile(fileId: string, newName: string): Promise<FileSystemItem> {
    const response = await axiosInstance.put(
      `/fs/operations/rename-file/${fileId}`,
      null,
      {
        params: { new_name: newName },
      }
    );
    return response.data;
  },

  // 重命名引用
  async renameReference(
    referenceId: string,
    newName: string
  ): Promise<FileSystemItem> {
    const response = await axiosInstance.put(
      `/fs/operations/rename-reference/${referenceId}`,
      null,
      {
        params: { new_name: newName },
      }
    );
    return response.data;
  },

  // 移动项目
  async moveItem(
    itemId: string,
    newParentId: string | null
  ): Promise<FileSystemItem> {
    const response = await axiosInstance.put(
      `/fs/operations/move-item/${itemId}`,
      null,
      {
        params: { new_parent_id: newParentId },
      }
    );
    return response.data;
  },

  // 批量处理操作
  async batchOperations(operations: FileSystemDiff[]): Promise<any> {
    const response = await axiosInstance.post('/fs/batch', { operations });
    return response.data;
  },

  // 保存文件系统更改
  async saveFileSystemChanges(
    oldItems: FileSystemItem[],
    newItems: FileSystemItem[]
  ): Promise<any> {
    const differences = checkItemsDiff(oldItems, newItems);
    if (differences.length === 0) {
      return { success: true, results: [] };
    }
    return this.batchOperations(differences);
  },
};

export { checkItemsDiff, FileSystemOperation };
export type { FileSystemDiff };
