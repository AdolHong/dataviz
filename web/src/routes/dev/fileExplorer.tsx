import { createFileRoute } from '@tanstack/react-router';
import { FileExplorer as FileExplorerComponent } from '@/components/dashboard/FileExplorer';

export const Route = createFileRoute('/dev/fileExplorer')({
  component: FileExplorer,
});

import { demoFileSystemData } from '@/data/demoFileSystem';
import { useEffect, useState } from 'react';
import { fsApi } from '@/api/fs';

function FileExplorer() {
  const [fileSystemData, setFileSystemData] = useState(demoFileSystemData);

  useEffect(() => {
    fsApi.getAllItems().then((items) => {
      setFileSystemData(items);
    });
  }, []);

  useEffect(() => {
    fsApi.getAllItems().then((items) => {
      setFileSystemData(items);
    });
  }, [fileSystemData]);

  return (
    <div className='parent-container'>
      <FileExplorerComponent
        fsItems={fileSystemData}
        setFsItems={(items) => {
          fsApi.saveFileSystemChanges(fileSystemData, items);
          setFileSystemData(items);
        }}
      />
    </div>
  );
}
