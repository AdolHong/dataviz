import React, { useRef, useState, useCallback, useMemo } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { FileText, FileUp, Eye, Download, RefreshCw, X } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { type DataSource } from '@/types';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table';
import Papa from 'papaparse';
import { toast } from 'sonner';
interface FileUploadAreaProps {
  dataSources: DataSource[];
  // files: Record<string, File[]>;
  // setFiles: (files: Record<string, File[]>) => void;

  setFileCache: (sourceId: string, file: File) => void;
  getFileCache: (sourceId: string) => File | null;
  removeFileCache: (sourceId: string) => void;
}

export function FileUploadArea({
  dataSources,
  // files,
  // setFiles,
  setFileCache,
  getFileCache,
  removeFileCache,
}: FileUploadAreaProps) {
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false);
  const [previewSource, setPreviewSource] = useState<DataSource | null>(null);
  const [previewTab, setPreviewTab] = useState<'demo' | 'uploaded'>('demo');
  const [sourceId2existFile, setSourceId2existFile] = useState<
    Record<string, boolean>
  >({});

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

  const handleFileChange = async (
    e: React.ChangeEvent<HTMLInputElement>,
    sourceId: string
  ) => {
    if (e.target.files && e.target.files.length > 0) {
      if (e.target.files[0].size > 1024 * 1024) {
        // 如果文件大小超过1mb，则不保存
        toast.error('文件大小超过1mb，请重新选择文件');
        return;
      }

      const content = await readFileContent(e.target.files[0]);
      setFileCache(sourceId, e.target.files[0]);
    }
  };

  const handleRemoveFile = (sourceId: string) => {
    removeFileCache(sourceId);

    // 清空文件输入框，以便重新上传相同的文件
    if (fileInputRefs.current[sourceId]) {
      fileInputRefs.current[sourceId]!.value = '';
    }
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

  return (
    <div className='space-y-4'>
      {/* CSV 数据源区域 */}
      {(uploaderSources.length > 0 || dataOnlySources.length > 0) && (
        <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'>
          {[...uploaderSources, ...dataOnlySources].map((source) => (
            <div
              key={source.id}
              className={`border rounded-md p-4 flex flex-col space-y-3 ${
                source.executor.type === 'csv_data' ? 'bg-muted/30' : ''
              }`}
            >
              <div className='flex items-center justify-between'>
                <div className='flex items-center space-x-2'>
                  <FileText size={16} className='text-primary' />
                  <h3 className='font-medium text-sm'>{source.name}</h3>
                </div>

                <div className='flex space-x-1'>
                  {/* 下载按钮 */}
                  <Button
                    variant='ghost'
                    size='icon'
                    className='h-6 w-6 hover:text-green-500'
                    title='下载数据'
                    onClick={(e) => {
                      e.preventDefault();
                      handleDownloadDemo(source);
                    }}
                  >
                    <Download size={14} />
                  </Button>

                  {/* 预览按钮 */}
                  <Button
                    variant='ghost'
                    size='icon'
                    className='h-6 w-6 hover:text-blue-500'
                    title='预览数据'
                    onClick={(e) => {
                      e.preventDefault();
                      handleShowPreview(
                        source,
                        source.executor.type === 'csv_uploader' &&
                          getFileCache(source.id)
                          ? 'uploaded'
                          : 'demo'
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

              {source.executor.type === 'csv_uploader' ? (
                getFileCache(source.id) ? (
                  <div className='space-y-2'>
                    <div className='flex items-center justify-between'>
                      <span className='text-sm truncate'>
                        {getFileCache(source.id)?.name}
                      </span>
                      <div className='flex space-x-1'>
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
                      {getFileCache(source.id)?.size
                        ? (getFileCache(source.id)?.size / 1024).toFixed(2)
                        : '未知'}{' '}
                      KB •{getFileCache(source.id)?.type || '未知类型'}
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
                )
              ) : (
                <div className='text-xs text-center italic text-muted-foreground py-2'>
                  (内置数据，无需上传)
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 数据预览对话框 */}
      <Dialog open={previewDialogOpen} onOpenChange={setPreviewDialogOpen}>
        <DialogContent className='min-w-[300px] max-w-[800px]'>
          <DialogHeader>
            <DialogTitle>
              {previewSource ? `${previewSource.name} 数据预览` : '数据预览'}
            </DialogTitle>
          </DialogHeader>

          {previewSource &&
          previewSource.executor.type === 'csv_uploader' &&
          getFileCache(previewSource.id) ? (
            <Tabs
              defaultValue={previewTab}
              className='min-w-[300px] max-w-[800px]'
            >
              <TabsList className='grid w-full grid-cols-2'>
                <TabsTrigger value='demo'>示例数据</TabsTrigger>
                <TabsTrigger value='uploaded'>已上传数据</TabsTrigger>
              </TabsList>
              <TabsContent value='demo'>
                <CSVPreview csvData={getSourceDemoData(previewSource)} />
              </TabsContent>
              <TabsContent value='uploaded' className='w-full'>
                <UploadedFilePreview
                  sourceId={previewSource.id}
                  sourceId2existFile={sourceId2existFile}
                  getFileCache={getFileCache}
                />
              </TabsContent>
            </Tabs>
          ) : (
            <div className='overflow-auto'>
              {previewSource && (
                <CSVPreview csvData={getSourceDemoData(previewSource)} />
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// 新增的 CSV 预览组件，直接使用 TanStack Table
function CSVPreview({ csvData }: { csvData: string }) {
  // 使用 useMemo 只解析一次 CSV 数据
  const { parsedData, totalRowCount } = useMemo(() => {
    try {
      const results = Papa.parse(csvData, { header: true });
      return {
        parsedData: results.data.slice(0, 5), // 最多显示 5 行
        totalRowCount: results.data.length,
      };
    } catch (error) {
      console.error('CSV 解析错误:', error);
      return {
        parsedData: [],
        totalRowCount: 0,
      };
    }
  }, [csvData]);

  // 如果没有数据，显示提示
  if (!parsedData.length) {
    return <div className='py-4 text-center'>没有可显示的数据</div>;
  }

  // 动态创建列
  const columns = useMemo(() => {
    if (parsedData.length === 0) return [];

    const firstRow = parsedData[0] as Record<string, unknown>;
    const columnHelper = createColumnHelper<Record<string, unknown>>();

    return Object.keys(firstRow).map((key) =>
      columnHelper.accessor(key, {
        header: key,
        cell: (info) => info.getValue() as React.ReactNode,
      })
    );
  }, [parsedData]);

  // 创建表格实例
  const table = useReactTable({
    data: parsedData as Record<string, unknown>[],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className='relative'>
      <div className='overflow-auto'>
        <div className='min-w-max'>
          <table className='border-collapse w-full'>
            <thead className='bg-muted sticky top-0'>
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className='border px-4 py-2 text-left whitespace-nowrap'
                      style={{ minWidth: '120px' }}
                    >
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className='border px-4 py-2 whitespace-nowrap overflow-hidden text-ellipsis'
                      style={{ maxWidth: '200px' }}
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className='text-right text-xs text-muted-foreground mt-2 pr-2'>
        显示 {parsedData.length} / {totalRowCount} 行
      </div>
    </div>
  );
}

// 修改 UploadedFilePreview 组件使用新的 CSVPreview 组件
function UploadedFilePreview({
  sourceId,
  sourceId2existFile,
  getFileCache,
}: {
  sourceId: string;
  sourceId2existFile: Record<string, boolean>;
  getFileCache: (sourceId: string) => File | null;
}) {
  const [fileContent, setFileContent] = useState<string>('');
  const [loading, setLoading] = useState(true);

  React.useEffect(() => {
    const loadContent = async () => {
      try {
        setLoading(true);
        const file = getFileCache(sourceId);
        if (!file) {
          setFileContent('');
          setLoading(false);
          return;
        }
        const content = await readFileContent(file);
        setFileContent(content || '');
      } catch (error) {
        console.error('读取文件失败', error);
        setFileContent('');
      } finally {
        setLoading(false);
      }
    };

    loadContent();
  }, [sourceId, sourceId2existFile]);

  if (loading) {
    return <div className='py-4 text-center'>正在加载文件内容...</div>;
  }

  if (!fileContent) {
    return <div className='py-4 text-center'>无法读取文件内容</div>;
  }

  return <CSVPreview csvData={fileContent} />;
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
