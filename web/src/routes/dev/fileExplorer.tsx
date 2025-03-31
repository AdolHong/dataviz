import { createFileRoute } from '@tanstack/react-router';
import { FileExplorer as FileExplorerComponent } from '@/components/dashboard/FileExplorer';

export const Route = createFileRoute('/dev/fileExplorer')({
  component: FileExplorer,
});

import { demoFileSystemData } from '@/data/demoFileSystem';
import { useState } from 'react';

function FileExplorer() {
  const [fileSystemData, setFileSystemData] = useState(demoFileSystemData);

  return (
    <FileExplorerComponent
      fsItems={fileSystemData}
      setFsItems={setFileSystemData}
    />
  );
}
