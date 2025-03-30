import React, { useState, useRef, useCallback } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Calendar } from '@/components/ui/calendar';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Calendar as CalendarIcon,
  X,
  ChevronUp,
  ChevronDown,
  Upload,
  Search,
  Check,
  FileUp,
  FileText,
  RefreshCw,
  Eye,
} from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';
import { type Parameter } from '@/types/models/parameter';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
} from '@/components/ui/command';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { CSVTable } from '@/components/CSVTable';
import type { DataSource } from '@/types';

interface ParameterQueryAreaProps {
  parameters: Parameter[];
  dataSources?: DataSource[];
  onSubmit: (
    values: Record<string, any>,
    files?: Record<string, File[]>
  ) => void;
}

export function ParameterQueryArea({
  parameters,
  dataSources = [],
  onSubmit,
}: ParameterQueryAreaProps) {
  const [values, setValues] = useState<Record<string, any>>({});
  const [files, setFiles] = useState<Record<string, File[]>>({});
  const [parametersExpanded, setParametersExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState<string>('parameters');
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false);
  const [previewSource, setPreviewSource] = useState<DataSource | null>(null);

  // 检查需要文件上传的数据源
  const csvDataSources = dataSources.filter(
    (ds) =>
      ds.executor.type === 'csv_uploader' || ds.executor.type === 'csv_data'
  );
  const requireFileUpload = csvDataSources.length > 0;

  const multiInputRef = useRef<HTMLInputElement>(null);
  // 修复 fileInputRefs 类型问题
  const fileInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const toggleParametersExpanded = () => {
    setParametersExpanded(!parametersExpanded);
  };

  const handleValueChange = (id: string, value: any) => {
    setValues((prev) => ({ ...prev, [id]: value }));
  };

  const handleFileChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    sourceId: string
  ) => {
    if (e.target.files && e.target.files.length > 0) {
      setFiles((prev) => ({
        ...prev,
        [sourceId]: Array.from(e.target.files!),
      }));
    }
  };

  const handleRemoveFile = (sourceId: string) => {
    setFiles((prev) => {
      const newFiles = { ...prev };
      delete newFiles[sourceId];
      return newFiles;
    });

    // 清空文件输入框，以便重新上传相同的文件
    if (fileInputRefs.current[sourceId]) {
      fileInputRefs.current[sourceId]!.value = '';
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(values, files);
  };

  // 显示数据预览对话框
  const handleShowPreview = useCallback((source: DataSource) => {
    setPreviewSource(source);
    setPreviewDialogOpen(true);
  }, []);

  // 设置文件输入引用的回调
  const setFileInputRef = useCallback(
    (el: HTMLInputElement | null, sourceId: string) => {
      fileInputRefs.current[sourceId] = el;
    },
    []
  );

  const getParameterLabel = (param: Parameter) => {
    if (param.alias) {
      return `${param.alias}(${param.name})`;
    }
    return param.name;
  };

  // 多输入框键盘事件处理
  const handleMultiInputKeyDown = (
    e: React.KeyboardEvent<HTMLInputElement>,
    param: Parameter
  ) => {
    if (e.key === 'Enter' && e.currentTarget.value.trim() !== '') {
      e.preventDefault();
      const newValue = e.currentTarget.value.trim();
      const currentValues = values[param.id] || [];
      handleValueChange(param.id, [...currentValues, newValue]);
      e.currentTarget.value = '';
    }
  };

  // 删除多输入框中的项
  const removeMultiInputItem = (param: Parameter, index: number) => {
    const currentValues = values[param.id] || [];
    const newValues = [...currentValues];
    newValues.splice(index, 1);
    handleValueChange(param.id, newValues);
  };

  const renderParameterInput = (param: Parameter) => {
    const label = getParameterLabel(param);

    const inputComponent = (() => {
      switch (param.config.type) {
        case 'single_select':
          return (
            <Select
              defaultValue={param.config.default}
              onValueChange={(value) => handleValueChange(param.id, value)}
            >
              <SelectTrigger className='w-full'>
                <SelectValue placeholder='请选择' />
              </SelectTrigger>
              <SelectContent>
                {param.config.choices.map((choice) => (
                  <SelectItem key={choice} value={choice}>
                    {choice}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          );

        case 'multi_select':
          return (
            <Popover>
              <PopoverTrigger asChild>
                <Button variant='outline' className='w-full justify-between'>
                  <span className='truncate'>
                    {values[param.id]?.length
                      ? `已选择 ${values[param.id].length} 项`
                      : '请选择'}
                  </span>
                  <ChevronDown className='ml-2 h-4 w-4 shrink-0 opacity-50' />
                </Button>
              </PopoverTrigger>
              <PopoverContent className='w-full p-0' align='start'>
                <Command>
                  <CommandInput placeholder='搜索选项...' />
                  <CommandEmpty>未找到结果</CommandEmpty>
                  <CommandGroup className='max-h-64 overflow-auto'>
                    {param.config.choices.map((choice) => {
                      const isSelected = (values[param.id] || []).includes(
                        choice
                      );
                      return (
                        <CommandItem
                          key={choice}
                          onSelect={() => {
                            const currentValues = values[param.id] || [];
                            const newValues = isSelected
                              ? currentValues.filter(
                                  (v: string) => v !== choice
                                )
                              : [...currentValues, choice];
                            handleValueChange(param.id, newValues);
                          }}
                        >
                          <div className='flex items-center gap-2 w-full'>
                            <div
                              className={cn(
                                'flex h-4 w-4 items-center justify-center rounded-sm border',
                                isSelected
                                  ? 'bg-primary border-primary'
                                  : 'opacity-50'
                              )}
                            >
                              {isSelected && (
                                <Check className='h-3 w-3 text-primary-foreground' />
                              )}
                            </div>
                            <span>{choice}</span>
                          </div>
                        </CommandItem>
                      );
                    })}
                  </CommandGroup>
                </Command>
              </PopoverContent>
            </Popover>
          );

        case 'date_picker':
          return (
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant='outline'
                  className={cn(
                    'w-full justify-start text-left font-normal',
                    !values[param.id] && 'text-muted-foreground'
                  )}
                >
                  <CalendarIcon className='mr-2 h-4 w-4' />
                  {values[param.id]
                    ? format(values[param.id], param.config.dateFormat)
                    : '选择日期'}
                </Button>
              </PopoverTrigger>
              <PopoverContent className='w-auto p-0'>
                <Calendar
                  mode='single'
                  selected={values[param.id]}
                  onSelect={(date) => handleValueChange(param.id, date)}
                  initialFocus
                />
              </PopoverContent>
            </Popover>
          );

        case 'multi_input':
          // 修复多输入
          const currentInputValues = values[param.id] || [];
          const defaultValues = param.config.default || [];
          const displayValues =
            currentInputValues.length > 0 ? currentInputValues : defaultValues;

          return (
            <div className='space-y-2'>
              <div>
                <Input
                  ref={multiInputRef}
                  placeholder='输入后按回车添加'
                  onKeyDown={(e) => handleMultiInputKeyDown(e, param)}
                />
              </div>
              {displayValues.length > 0 && (
                <div className='flex flex-wrap gap-1 mt-2'>
                  {displayValues.map((value: string, index: number) => (
                    <Badge
                      key={index}
                      variant='secondary'
                      className='flex items-center gap-1'
                    >
                      {value}
                      <X
                        size={14}
                        className='cursor-pointer hover:text-destructive'
                        onClick={(e) => {
                          e.stopPropagation();
                          removeMultiInputItem(param, index);
                        }}
                      />
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          );

        case 'single_input':
        default:
          return (
            <Input
              defaultValue={param.config.default}
              onChange={(e) => handleValueChange(param.id, e.target.value)}
            />
          );
      }
    })();

    return (
      <div className='space-y-2'>
        <div className='flex items-center gap-1'>
          {param.description ? (
            <TooltipProvider delayDuration={1000}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Label htmlFor={param.id}>{label}</Label>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{param.description}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ) : (
            <Label htmlFor={param.id}>{label}</Label>
          )}
        </div>
        {inputComponent}
      </div>
    );
  };

  // 获取CSV数据源的预览数据
  const getSourcePreviewData = (source: DataSource): string => {
    if (source.executor.type === 'csv_uploader') {
      return source.executor.demoData || '';
    } else if (source.executor.type === 'csv_data') {
      return source.executor.data || '';
    }
    return '';
  };

  return (
    <Card className='w-full'>
      <CardContent className='pt-4 pb-2'>
        <form onSubmit={handleSubmit}>
          {parametersExpanded ? (
            <Tabs
              defaultValue='parameters'
              value={activeTab}
              onValueChange={setActiveTab}
              className='w-full'
            >
              <div className='flex justify-between items-center mb-2'>
                <TabsList>
                  <TabsTrigger
                    value='parameters'
                    className='flex items-center gap-1'
                  >
                    <Search size={14} />
                    <span>查询参数</span>
                  </TabsTrigger>
                  {requireFileUpload && (
                    <TabsTrigger
                      value='upload'
                      className='flex items-center gap-1'
                    >
                      <Upload size={14} />
                      <span>文件上传 ({csvDataSources.length})</span>
                    </TabsTrigger>
                  )}
                </TabsList>
                <Button
                  variant='ghost'
                  size='sm'
                  onClick={toggleParametersExpanded}
                  className='h-8 px-2'
                >
                  <ChevronUp size={16} className='text-muted-foreground' />
                </Button>
              </div>

              <TabsContent value='parameters' className='mt-2 space-y-4'>
                <div className='grid grid-cols-2 md:grid-cols-4 gap-3'>
                  {parameters.map((param) => (
                    <div key={param.id} className='col-span-1'>
                      {renderParameterInput(param)}
                    </div>
                  ))}
                </div>
                <div className='flex justify-end'>
                  <Button type='submit'>查询</Button>
                </div>
              </TabsContent>

              {requireFileUpload && (
                <TabsContent value='upload' className='mt-2 space-y-4'>
                  <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'>
                    {csvDataSources.map((source) => (
                      <div
                        key={source.id}
                        className='border rounded-md p-4 flex flex-col space-y-3'
                      >
                        <div className='flex items-center justify-between'>
                          <div className='flex items-center space-x-2'>
                            <FileText size={16} className='text-primary' />
                            <h3 className='font-medium text-sm'>
                              {source.name}
                            </h3>
                          </div>

                          <div className='flex space-x-1'>
                            <Button
                              variant='ghost'
                              size='icon'
                              className='h-6 w-6 hover:text-blue-500'
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
                              {(files[source.id][0].size / 1024).toFixed(2)} KB
                              • {files[source.id][0].type || '未知类型'}
                            </div>
                          </div>
                        ) : (
                          <div
                            className='border-2 border-dashed rounded-md p-3 text-center hover:border-primary/50 transition-colors cursor-pointer'
                            onClick={() =>
                              fileInputRefs.current[source.id]?.click()
                            }
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
                              <FileUp
                                size={16}
                                className='text-muted-foreground'
                              />
                              <span className='text-xs font-medium'>
                                点击上传
                              </span>
                              <span className='text-xs text-muted-foreground'>
                                支持CSV文件
                              </span>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {Object.keys(files).length > 0 && (
                    <div className='flex justify-between items-center mt-4'>
                      <Button
                        variant='outline'
                        size='sm'
                        onClick={(e) => {
                          e.preventDefault();
                          setFiles({});
                          Object.keys(fileInputRefs.current).forEach((key) => {
                            const inputRef = fileInputRefs.current[key];
                            if (inputRef) {
                              inputRef.value = '';
                            }
                          });
                        }}
                      >
                        清空所有
                      </Button>
                      <Button type='submit'>应用</Button>
                    </div>
                  )}
                </TabsContent>
              )}
            </Tabs>
          ) : (
            <div className='flex justify-between items-center'>
              <Button type='submit' className='w-full'>
                查询
              </Button>
              <Button
                variant='ghost'
                size='sm'
                onClick={toggleParametersExpanded}
                className='h-8 px-2 ml-2'
              >
                <ChevronDown size={16} className='text-muted-foreground' />
              </Button>
            </div>
          )}
        </form>
      </CardContent>

      {/* 添加数据预览对话框 */}
      <Dialog open={previewDialogOpen} onOpenChange={setPreviewDialogOpen}>
        <DialogContent className='sm:max-w-[800px]'>
          <DialogHeader>
            <DialogTitle>
              {previewSource ? `${previewSource.name} 数据预览` : '数据预览'}
            </DialogTitle>
          </DialogHeader>
          <div className='max-h-[500px] overflow-auto'>
            {previewSource && (
              <CSVTable csvData={getSourcePreviewData(previewSource)} />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
