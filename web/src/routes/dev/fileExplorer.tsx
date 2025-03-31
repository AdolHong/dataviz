import { createFileRoute } from '@tanstack/react-router';
import { FileExplorer as FileExplorerComponent } from '@/components/dashboard/FileExplorer';

export const Route = createFileRoute('/dev/fileExplorer')({
  component: FileExplorer,
});

import { useEffect, useState } from 'react';
import { fsApi } from '@/api/fs';
import type { FileSystemItem } from '@/types/models/fileSystem';

function FileExplorer() {
  const [fileSystemItems, setFileSystemItems] = useState<FileSystemItem[]>([]);
  const [isReloadFileSystem, setIsReloadFileSystem] = useState(false);

  // 初始化加载文件系统项目
  useEffect(() => {
    const loadItems = async () => {
      const data = await fsApi.getAllItems();

      setFileSystemItems(data);
    };
    loadItems();
  }, []);

  // 监听 isReloadFileSystem 状态，重新加载文件系统项目
  useEffect(() => {
    if (isReloadFileSystem) {
      fsApi.getAllItems().then((items) => {
        setFileSystemItems(items);
        setIsReloadFileSystem(false); // 重置状态
      });
    }
  }, [isReloadFileSystem]);

  return (
    <FileExplorerComponent
      fsItems={fileSystemItems}
      setFsItems={(items) => {
        fsApi.saveFileSystemChanges(fileSystemItems, items).then(() => {
          setIsReloadFileSystem(true);
        });
      }}
    />
  );
}
