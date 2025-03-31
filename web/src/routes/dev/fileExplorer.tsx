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
  const [fileSystemData, setFileSystemData] = useState<FileSystemItem[]>([]);

  // 是否用demo数据进行展示
  const isDemo = true;

  useEffect(() => {
    if (isDemo) {
      setFileSystemData(demoFileSystemData);
    } else {
      fsApi.getAllItems().then((items) => {
        setFileSystemData(items);
      });
    }
  }, []);

  useEffect(() => {
    if (!isDemo) {
      fsApi.getAllItems().then((items) => {
        setFileSystemData(items);
      });
    }
  }, [fileSystemData]);

  return (
    <FileExplorerComponent
      fsItems={fileSystemData}
      setFsItems={(items) => {
        fsApi.saveFileSystemChanges(fileSystemData, items);
        setFileSystemData(items);
      }}
    />
  );
}
