import React, { useRef, useState, useCallback } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { FileText, FileUp, Eye, Download, RefreshCw, X } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { CSVTable } from '@/components/CSVTable';
import { type DataSource } from '@/types';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface FileUploadAreaProps {
  dataSources: DataSource[];
  onFilesChange: (files: Record<string, File[]>) => void;
}

export function FileUploadArea({
  dataSources,
  onFilesChange,
}: FileUploadAreaProps) {
  const [files, setFiles] = useState<Record<string, File[]>>({});
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false);
  const [previewSource, setPreviewSource] = useState<DataSource | null>(null);
  const [previewTab, setPreviewTab] = useState<'demo' | 'uploaded'>('demo');

  // 筛选不同类型的数据源
  const uploaderSources = dataSources.filter(
    (ds) => ds.executor.type === 'csv_uploader'
  );
  const dataOnlySources = dataSources.filter(
    (ds) => ds.executor.type === 'csv_data'
  );

  const fileInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  // 设置文件输入引用的回调
  const setFileInputRef = useCallback(
    (el: HTMLInputElement | null, sourceId: string) => {
      fileInputRefs.current[sourceId] = el;
    },
    []
  );

  const handleFileChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    sourceId: string
  ) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = {
        ...files,
        [sourceId]: Array.from(e.target.files),
      };
      setFiles(newFiles);
      onFilesChange(newFiles);
    }
  };

  const handleRemoveFile = (sourceId: string) => {
    const newFiles = { ...files };
    delete newFiles[sourceId];
    setFiles(newFiles);
    onFilesChange(newFiles);

    // 清空文件输入框，以便重新上传相同的文件
    if (fileInputRefs.current[sourceId]) {
      fileInputRefs.current[sourceId]!.value = '';
    }
  };

  const handleClearAllFiles = (e: React.MouseEvent) => {
    e.preventDefault();
    setFiles({});
    onFilesChange({});
    Object.keys(fileInputRefs.current).forEach((key) => {
      const inputRef = fileInputRefs.current[key];
      if (inputRef) {
        inputRef.value = '';
      }
    });
  };

  // 显示数据预览对话框
  const handleShowPreview = useCallback(
    (source: DataSource, initialTab: 'demo' | 'uploaded' = 'demo') => {
      setPreviewSource(source);
      setPreviewTab(initialTab);
      setPreviewDialogOpen(true);
    },
    []
  );

  // 获取CSV数据源的预览数据
  const getSourceDemoData = (source: DataSource): string => {
    if (source.executor.type === 'csv_uploader') {
      return source.executor.demoData || '';
    } else if (source.executor.type === 'csv_data') {
      return source.executor.data || '';
    }
    return '';
  };

  // 下载Demo数据
  const handleDownloadDemo = (source: DataSource) => {
    const demoData = getSourceDemoData(source);
    if (!demoData) return;

    const blob = new Blob([demoData], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${source.name}_demo.csv`;
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  // 从上传的文件中读取内容
  const getUploadedFileContent = async (sourceId: string): Promise<string> => {
    const sourceFiles = files[sourceId];
    if (!sourceFiles || sourceFiles.length === 0) return '';

    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        resolve((e.target?.result as string) || '');
      };
      reader.readAsText(sourceFiles[0]);
    });
  };

  return (
    <div className='space-y-4'>
      {/* CSV上传区 */}
      {uploaderSources.length > 0 && (
        <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'>
          {uploaderSources.map((source) => (
            <div
              key={source.id}
              className='border rounded-md p-4 flex flex-col space-y-3'
            >
              <div className='flex items-center justify-between'>
                <div className='flex items-center space-x-2'>
                  <FileText size={16} className='text-primary' />
                  <h3 className='font-medium text-sm'>{source.name}</h3>
                </div>

                <div className='flex space-x-1'>
                  <Button
                    variant='ghost'
                    size='icon'
                    className='h-6 w-6 hover:text-green-500'
                    title='下载示例数据'
                    onClick={(e) => {
                      e.preventDefault();
                      handleDownloadDemo(source);
                    }}
                  >
                    <Download size={14} />
                  </Button>
                  <Button
                    variant='ghost'
                    size='icon'
                    className='h-6 w-6 hover:text-blue-500'
                    title='预览数据'
                    onClick={(e) => {
                      e.preventDefault();
                      handleShowPreview(
                        source,
                        files[source.id] ? 'uploaded' : 'demo'
                      );
                    }}
                  >
                    <Eye size={14} />
                  </Button>
                </div>
              </div>

              <div className='text-xs text-muted-foreground'>
                数据别名: {source.alias}
              </div>

              {files[source.id] ? (
                <div className='space-y-2'>
                  <div className='flex items-center justify-between'>
                    <span className='text-sm truncate'>
                      {files[source.id][0].name}
                    </span>
                    <div className='flex space-x-1'>
                      <Button
                        variant='ghost'
                        size='icon'
                        className='h-7 w-7'
                        title='重新上传'
                        onClick={(e) => {
                          e.preventDefault();
                          fileInputRefs.current[source.id]?.click();
                        }}
                      >
                        <RefreshCw size={14} />
                      </Button>
                      <Button
                        variant='ghost'
                        size='icon'
                        className='h-7 w-7 text-destructive'
                        title='删除'
                        onClick={(e) => {
                          e.preventDefault();
                          handleRemoveFile(source.id);
                        }}
                      >
                        <X size={14} />
                      </Button>
                    </div>
                  </div>
                  <div className='text-xs text-muted-foreground'>
                    {(files[source.id][0].size / 1024).toFixed(2)} KB •{' '}
                    {files[source.id][0].type || '未知类型'}
                  </div>
                </div>
              ) : (
                <div
                  className='border-2 border-dashed rounded-md p-3 text-center hover:border-primary/50 transition-colors cursor-pointer'
                  onClick={() => fileInputRefs.current[source.id]?.click()}
                >
                  <Input
                    ref={(el) => setFileInputRef(el, source.id)}
                    id={`file-upload-${source.id}`}
                    type='file'
                    accept='.csv,.txt'
                    className='hidden'
                    onChange={(e) => handleFileChange(e, source.id)}
                  />
                  <div className='flex flex-col items-center gap-1'>
                    <FileUp size={16} className='text-muted-foreground' />
                    <span className='text-xs font-medium'>点击上传</span>
                    <span className='text-xs text-muted-foreground'>
                      支持CSV文件
                    </span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* CSV数据区(无需上传) */}
      {dataOnlySources.length > 0 && (
        <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-4'>
          {dataOnlySources.map((source) => (
            <div
              key={source.id}
              className='border rounded-md p-4 flex flex-col space-y-3 bg-muted/30'
            >
              <div className='flex items-center justify-between'>
                <div className='flex items-center space-x-2'>
                  <FileText size={16} className='text-primary' />
                  <h3 className='font-medium text-sm'>{source.name}</h3>
                </div>

                <div className='flex space-x-1'>
                  <Button
                    variant='ghost'
                    size='icon'
                    className='h-6 w-6 hover:text-blue-500'
                    title='预览数据'
                    onClick={(e) => {
                      e.preventDefault();
                      handleShowPreview(source);
                    }}
                  >
                    <Eye size={14} />
                  </Button>
                </div>
              </div>

              <div className='text-xs text-muted-foreground'>
                数据别名: {source.alias}
              </div>

              <div className='text-xs text-center italic text-muted-foreground py-2'>
                (内置数据，无需上传)
              </div>
            </div>
          ))}
        </div>
      )}

      {Object.keys(files).length > 0 && (
        <div className='flex justify-end items-center mt-4'>
          <Button variant='outline' size='sm' onClick={handleClearAllFiles}>
            清空所有
          </Button>
        </div>
      )}

      {/* 数据预览对话框 */}
      <Dialog open={previewDialogOpen} onOpenChange={setPreviewDialogOpen}>
        <DialogContent className='max-w-[800px]'>
          <DialogHeader>
            <DialogTitle>
              {previewSource ? `${previewSource.name} 数据预览` : '数据预览'}
            </DialogTitle>
          </DialogHeader>

          {previewSource &&
          previewSource.executor.type === 'csv_uploader' &&
          files[previewSource.id] ? (
            <Tabs defaultValue={previewTab} className='max-w-[800px]'>
              <TabsList className='grid w-full grid-cols-2'>
                <TabsTrigger value='demo'>示例数据</TabsTrigger>
                <TabsTrigger value='uploaded'>已上传数据</TabsTrigger>
              </TabsList>
              <TabsContent value='demo' className='max-h-[500px] overflow-auto'>
                <CSVTable csvData={getSourceDemoData(previewSource)} />
              </TabsContent>
              <TabsContent
                value='uploaded'
                className='max-h-[500px] overflow-auto'
              >
                <UploadedFilePreview
                  sourceId={previewSource.id}
                  files={files}
                />
              </TabsContent>
            </Tabs>
          ) : (
            <div className='max-h-[500px] overflow-auto'>
              {previewSource && (
                <CSVTable csvData={getSourceDemoData(previewSource)} />
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// 用于预览上传的文件内容的组件
function UploadedFilePreview({
  sourceId,
  files,
}: {
  sourceId: string;
  files: Record<string, File[]>;
}) {
  const [fileContent, setFileContent] = useState<string>('');
  const [loading, setLoading] = useState(true);

  React.useEffect(() => {
    const loadContent = async () => {
      try {
        setLoading(true);
        const content = await readFileContent(files[sourceId]?.[0]);
        setFileContent(content || '');
      } catch (error) {
        console.error('读取文件失败', error);
        setFileContent('');
      } finally {
        setLoading(false);
      }
    };

    loadContent();
  }, [sourceId, files]);

  if (loading) {
    return <div className='py-4 text-center'>正在加载文件内容...</div>;
  }

  if (!fileContent) {
    return <div className='py-4 text-center'>无法读取文件内容</div>;
  }

  return <CSVTable csvData={fileContent} />;
}

// 从文件读取内容
function readFileContent(file?: File): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!file) {
      resolve('');
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      resolve((e.target?.result as string) || '');
    };
    reader.onerror = (e) => {
      reject(e);
    };
    reader.readAsText(file);
  });
}
