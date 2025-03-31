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

export { checkItemsDiff, FileSystemOperation };
