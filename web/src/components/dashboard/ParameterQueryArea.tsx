import React, { useState, useEffect } from 'react';
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { X, ChevronUp, ChevronDown, Upload, Search, Check } from 'lucide-react';
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
import { FileUploadArea } from '@/components/dashboard/FileUploadArea';
import type { DataSource } from '@/types';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DatePicker } from '@/components/ui/datepicker';
import { Card } from '../ui/card';
import { CardContent } from '../ui/card';
import { type DatePickerParamConfig } from '@/types/models/parameter';
import dayjs from 'dayjs';
import { useTabsSessionStore } from '@/lib/store/useTabsSessionStore';
import { type FileCache } from '@/lib/store/useFileSessionStore';

interface ParameterQueryAreaProps {
  isQuerying: boolean;
  parameters: Parameter[];
  dataSources?: DataSource[];
  onSubmit: (
    values: Record<string, any>,
    files?: Record<string, FileCache>
  ) => void;
  onEditReport: () => void;
  cachedParamValues: Record<string, any>;
  cachedFiles: Record<string, FileCache>;
}

import { parseDynamicDate } from '@/utils/parser';

export function ParameterQueryArea({
  isQuerying,
  parameters,
  dataSources = [],
  onSubmit,
  onEditReport,
  cachedParamValues,
  cachedFiles,
}: ParameterQueryAreaProps) {
  const [parametersExpanded, setParametersExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState<string>('parameters');
  const [selectedDataSourceIndex, setSelectedDataSourceIndex] = useState<
    number | null
  >(null);

  const [values, setValues] = useState<Record<string, any>>({});
  const [files, setFiles] = useState<Record<string, FileCache>>({});
  const [nameToChoices, setNameToChoices] = useState<
    Record<string, Record<string, string>[]>
  >({});

  // 使用 store 来管理标签页
  const { activeTabId } = useTabsSessionStore();

  // 检查需要文件上传的数据源
  const csvDataSources = dataSources.filter(
    (ds) =>
      ds.executor.type === 'csv_uploader' || ds.executor.type === 'csv_data'
  );
  const requireFileUpload = csvDataSources.length > 0;

  // 使用 useEffect 在初始渲染时设置默认值
  useEffect(() => {
    // 初始化参数值
    initialValues();

    // 初始化文件
    initialChoices();
  }, [parameters]);

  const initialValues = () => {
    if (values && Object.keys(values).length === 0) {
      const initialValues: Record<string, any> = {};
      parameters.forEach((param) => {
        // 对于多选和多输入类型，使用默认数组
        if (
          param.config.type === 'multi_select' ||
          param.config.type === 'multi_input'
        ) {
          const defaultVal = param.config.default || [];
          const parsedVal = defaultVal.map((val: string) =>
            parseDynamicDate(val)
          );
          initialValues[param.name] = parsedVal;
        }
        // 对于单选和单输入类型，使用默认值
        else if (
          param.config.type === 'single_select' ||
          param.config.type === 'single_input' ||
          param.config.type === 'date_picker'
        ) {
          const defaultVal = param.config.default;
          const parseVal = parseDynamicDate(defaultVal);
          initialValues[param.name] = parseVal;
        }
      });

      const newValues = {
        ...initialValues,
        ...cachedParamValues,
      };
      setValues(newValues);
      console.log('newValues, ', newValues);
    }
  };

  const initialChoices = () => {
    parameters.forEach((param) => {
      if (
        param.config.type === 'single_select' ||
        param.config.type === 'multi_select'
      ) {
        const choices: Record<string, string>[] = param.config.choices;
        const newChoices = choices.map((choice) => {
          return {
            key: choice.key,
            value: parseDynamicDate(choice.value),
          };
        });

        nameToChoices[param.name] = newChoices;
      }
    });
    setNameToChoices(nameToChoices);
    console.log('nameToChoices, ', nameToChoices);
  };

  const toggleParametersExpanded = () => {
    setParametersExpanded(!parametersExpanded);
  };

  const handleValueChange = (id: string, value: any) => {
    const newValues = { ...values, [id]: value };
    setValues(newValues);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    console.log('sm??, ');
    if (!activeTabId) {
      toast.error('请先打开一个标签页');
      return;
    }

    if (
      requireFileUpload &&
      Object.keys(files).length !== csvDataSources.length
    ) {
      toast.error('请上传文件');
      return;
    }

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
      const currentValues = values[param.name] || [];

      // 检查是否已存在该值
      if (!currentValues.includes(newValue)) {
        handleValueChange(param.name, [...currentValues, newValue]);
        e.currentTarget.value = '';
      } else {
        // 可选：添加重复值的提示
        toast.warning('不允许添加重复值');
      }
    }
  };

  // 删除多输入框中的项
  const removeMultiInputItem = (param: Parameter, index: number) => {
    const currentValues = values[param.name] || [];
    const newValues = [...currentValues];
    newValues.splice(index, 1);
    handleValueChange(param.name, newValues);
  };

  const renderParameterInput = (param: Parameter) => {
    const label = getParameterLabel(param);

    const inputComponent = (() => {
      switch (param.config.type) {
        case 'single_select':
          return (
            <Select
              defaultValue={param.config.default}
              onValueChange={(value) => handleValueChange(param.name, value)}
            >
              <SelectTrigger className='w-full'>
                <SelectValue placeholder='请选择' />
              </SelectTrigger>
              <SelectContent>
                {nameToChoices &&
                  nameToChoices[param.name] &&
                  nameToChoices[param.name].map((choice) => (
                    <SelectItem key={choice.key} value={choice.value}>
                      {choice.value}
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
                    {values[param.name]?.length
                      ? `已选择 ${values[param.name].length} 项`
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
                    {nameToChoices &&
                      nameToChoices[param.name] &&
                      nameToChoices[param.name].map((choice) => {
                        // 使用 param.config.default 初始化多选值
                        const initialValues = param.config.default || [];
                        const isSelected = (
                          values[param.name] || initialValues
                        ).includes(choice);

                        return (
                          <CommandItem
                            key={choice.key}
                            onSelect={() => {
                              const currentValues =
                                values[param.name] || initialValues;
                              const newValues = isSelected
                                ? currentValues.filter(
                                    (v: string) => v !== choice.value
                                  )
                                : [...currentValues, choice.value];
                              handleValueChange(param.name, newValues);
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
                              <span>{choice.value}</span>
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
            <DatePicker
              date={
                values[param.name] ? new Date(values[param.name]) : undefined
              }
              setDate={(date) => {
                if (date) {
                  let dateFormat = (param.config as DatePickerParamConfig)
                    .dateFormat;
                  dateFormat =
                    dateFormat === 'YYYYMMDD' ? 'YYYYMMDD' : 'YYYY-MM-DD';

                  // 使用 dayjs 替换 toLocaleDateString
                  const dateString = dayjs(date).format(dateFormat);
                  handleValueChange(param.name, dateString);
                } else {
                  handleValueChange(param.name, '');
                }
              }}
            />
          );

        case 'multi_input':
          return (
            <div className='space-y-2'>
              <Input
                placeholder={`输入${param.name}（按回车添加）`}
                onKeyDown={(e) => handleMultiInputKeyDown(e, param)}
              />
              <div className='flex flex-wrap gap-2 mb-2'>
                {(values[param.name] || []).map(
                  (value: string, index: number) => (
                    <div
                      key={`${value}-${index}`}
                      className='flex items-center bg-muted rounded-md px-2 py-1 text-xs'
                    >
                      <span className='mr-2'>{value}</span>
                      <Button
                        variant='ghost'
                        size='icon'
                        className='h-4 w-4 hover:bg-destructive/20'
                        onClick={() => removeMultiInputItem(param, index)}
                      >
                        <X size={12} />
                      </Button>
                    </div>
                  )
                )}
              </div>
            </div>
          );

        case 'single_input':
        default:
          return (
            <Input
              defaultValue={values[param.name] || ''}
              onChange={(e) => handleValueChange(param.name, e.target.value)}
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
                  <Label htmlFor={param.name}>{label}</Label>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{param.description}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ) : (
            <Label htmlFor={param.name}>{label}</Label>
          )}
        </div>
        {inputComponent}
      </div>
    );
  };

  return (
    <Card className='w-full'>
      <CardContent>
        <form onSubmit={handleSubmit}>
          <Tabs
            defaultValue='parameters'
            value={activeTab}
            onValueChange={setActiveTab}
          >
            {/* tabs */}
            <div className='flex justify-between items-center mb-2 '>
              <div className='flex items-center'>
                <TabsList>
                  <TabsTrigger
                    value='parameters'
                    className='flex items-center gap-1'
                  >
                    <Search size={14} />
                    查询参数 ({parameters.length})
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
                <div className='flex space-x-2 ml-4'>
                  {dataSources.map((source, index) => (
                    <button
                      key={source.id}
                      type='button'
                      onClick={() => setSelectedDataSourceIndex(index)}
                      className='w-3 h-3 rounded-full bg-gray-300 shadow-sm hover:bg-gray-400 cursor-pointer'
                    />
                  ))}
                </div>
              </div>
              <div className='flex items-center space-x-2'>
                <Button
                  type='submit'
                  size='sm'
                  className='h-8 w-15 px-2'
                  disabled={isQuerying}
                >
                  查询
                </Button>
                <Button
                  variant='outline'
                  size='sm'
                  className='h-8 w-15 px-2'
                  onClick={onEditReport}
                  type='button'
                >
                  编辑
                </Button>

                <Button
                  variant='ghost'
                  size='sm'
                  onClick={toggleParametersExpanded}
                  className='border-1'
                  type='button'
                >
                  {parametersExpanded ? (
                    <ChevronUp size={16} className='text-muted-foreground' />
                  ) : (
                    <ChevronDown size={16} className='text-muted-foreground' />
                  )}
                </Button>
              </div>
            </div>

            {/* 参数 */}
            {parametersExpanded ? (
              <div>
                <TabsContent value='parameters' className='mt-2 space-y-4'>
                  <div className='grid grid-cols-2 md:grid-cols-4 gap-x-10 gap-y-3'>
                    {parameters.map((param) => (
                      <div key={param.name} className='col-span-1'>
                        {renderParameterInput(param)}
                      </div>
                    ))}
                  </div>
                </TabsContent>

                {requireFileUpload && (
                  <TabsContent value='upload' className='mt-2'>
                    <FileUploadArea
                      dataSources={csvDataSources}
                      files={files}
                      setFiles={setFiles}
                      cachedFiles={cachedFiles}
                    />
                  </TabsContent>
                )}
              </div>
            ) : null}
          </Tabs>
        </form>

        {/* 数据源详情对话框 */}
        <Dialog
          open={selectedDataSourceIndex !== null}
          onOpenChange={() => setSelectedDataSourceIndex(null)}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>
                {selectedDataSourceIndex !== null
                  ? `数据源: ${dataSources[selectedDataSourceIndex].name}`
                  : '数据源详情'}
              </DialogTitle>
            </DialogHeader>
            {/* 后续可以在这里添加更多详细信息 */}
            <div className='text-muted-foreground'>数据源详情 - 待完善</div>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}
