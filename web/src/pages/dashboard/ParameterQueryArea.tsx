import React, { useState, useRef } from 'react';
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
import { FileUploadArea } from '@/pages/dashboard/FileUploadArea';
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

  // 检查需要文件上传的数据源
  const csvDataSources = dataSources.filter(
    (ds) =>
      ds.executor.type === 'csv_uploader' || ds.executor.type === 'csv_data'
  );
  const requireFileUpload = csvDataSources.length > 0;

  const multiInputRef = useRef<HTMLInputElement>(null);

  const toggleParametersExpanded = () => {
    setParametersExpanded(!parametersExpanded);
  };

  const handleValueChange = (id: string, value: any) => {
    setValues((prev) => ({ ...prev, [id]: value }));
  };

  const handleFilesChange = (newFiles: Record<string, File[]>) => {
    setFiles(newFiles);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(values, files);
  };

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
                <TabsContent value='upload' className='mt-2'>
                  <FileUploadArea
                    dataSources={csvDataSources}
                    onFilesChange={handleFilesChange}
                  />
                  <div className='flex justify-end mt-4'>
                    <Button type='submit'>应用</Button>
                  </div>
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
    </Card>
  );
}
