import { createFileRoute } from '@tanstack/react-router';
import { FileExplorer as FileExplorerComponent } from '@/components/dashboard/FileExplorer';

export const Route = createFileRoute('/dev/fileExplorer')({
  component: FileExplorer,
});

import { demoFileSystemData } from '@/data/demoFileSystem';
import { useEffect, useState } from 'react';
import { fsApi } from '@/api/fs';
import type { FileSystemItem } from '@/types/models/fileSystem';

function FileExplorer() {
  const [fileSystemItems, setFileSystemItems] = useState<FileSystemItem[]>([]);

  // 是否用demo数据进行展示
  const isDemo = false;

  useEffect(() => {
    if (isDemo) {
      setFileSystemItems(demoFileSystemData);
    } else {
      fsApi.getAllItems().then((items) => {
        setFileSystemItems(items);
      });
    }
  }, []);

  useEffect(() => {
    if (!isDemo) {
      fsApi.getAllItems().then((items) => {
        setFileSystemItems(items);
      });
    }
  }, [fileSystemItems]);

  return (
    <FileExplorerComponent
      fsItems={fileSystemItems}
      setFsItems={(items) => {
        fsApi.saveFileSystemChanges(fileSystemItems, items);
        setFileSystemItems(items);
      }}
    />
  );
}
