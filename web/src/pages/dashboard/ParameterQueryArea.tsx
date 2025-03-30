import React, { useState, useRef, KeyboardEvent } from 'react';
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
  Plus,
  ChevronUp,
  ChevronDown,
  Upload,
  Search,
  Check,
} from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';
import { Checkbox } from '@/components/ui/checkbox';
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

interface ParameterQueryAreaProps {
  parameters: Parameter[];
  onSubmit: (values: Record<string, any>) => void;
  requireFileUpload?: boolean;
}

export function ParameterQueryArea({
  parameters,
  onSubmit,
  requireFileUpload = false,
}: ParameterQueryAreaProps) {
  const [values, setValues] = useState<Record<string, any>>({});
  const [files, setFiles] = useState<File[]>([]);
  const [parametersExpanded, setParametersExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState<string>('parameters');

  // 多输入引用
  const multiInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const toggleParametersExpanded = () => {
    setParametersExpanded(!parametersExpanded);
  };

  const handleValueChange = (id: string, value: any) => {
    setValues((prev) => ({ ...prev, [id]: value }));
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(values);
  };

  const getParameterLabel = (param: Parameter) => {
    if (param.alias) {
      return `${param.alias}(${param.name})`;
    }
    return param.name;
  };

  // 多输入框键盘事件处理
  const handleMultiInputKeyDown = (
    e: KeyboardEvent<HTMLInputElement>,
    param: Parameter
  ) => {
    if (e.key === 'Enter' && e.currentTarget.value.trim() !== '') {
      e.preventDefault();
      const newValue = e.currentTarget.value.trim();
      const currentValues = values[param.id] || param.config.default || [];
      handleValueChange(param.id, [...currentValues, newValue]);
      e.currentTarget.value = '';
    }
  };

  // 删除多输入框中的项
  const removeMultiInputItem = (param: Parameter, index: number) => {
    const currentValues = values[param.id] || param.config.default || [];
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
          // 改为下拉选择形式
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
          // 改为回车添加的输入方式
          return (
            <div className='space-y-2'>
              <div>
                <Input
                  ref={(el) => (multiInputRefs.current[param.id] = el)}
                  placeholder='输入后按回车添加'
                  onKeyDown={(e) => handleMultiInputKeyDown(e, param)}
                />
              </div>
              {(values[param.id]?.length > 0 ||
                param.config.default?.length > 0) && (
                <div className='flex flex-wrap gap-1 mt-2'>
                  {(values[param.id] || param.config.default || []).map(
                    (value: string, index: number) => (
                      <Badge
                        key={index}
                        variant='secondary'
                        className='flex items-center gap-1'
                      >
                        {value}
                        <X
                          size={14}
                          className='cursor-pointer'
                          onClick={() => removeMultiInputItem(param, index)}
                        />
                      </Badge>
                    )
                  )}
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
                      <span>文件上传</span>
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
                  <div className='space-y-4'>
                    <div className='space-y-2'>
                      <div className='border-2 border-dashed rounded-md p-6 text-center hover:border-primary/50 transition-colors'>
                        <Input
                          id='file-upload'
                          type='file'
                          multiple
                          className='hidden'
                          onChange={handleFileChange}
                        />
                        <Label
                          htmlFor='file-upload'
                          className='cursor-pointer block'
                        >
                          <div className='flex flex-col items-center gap-2'>
                            <Upload
                              size={20}
                              className='text-muted-foreground'
                            />
                            <span className='text-sm font-medium'>
                              点击或拖拽文件到此处上传
                            </span>
                            <span className='text-xs text-muted-foreground'>
                              支持多文件上传
                            </span>
                          </div>
                        </Label>
                      </div>
                      {files.length > 0 && (
                        <div className='mt-4 space-y-2'>
                          <p className='text-sm font-medium'>
                            已选择的文件 ({files.length}):
                          </p>
                          <ul className='text-sm max-h-40 overflow-y-auto space-y-1'>
                            {files.map((file, index) => (
                              <li
                                key={index}
                                className='text-muted-foreground truncate flex items-center gap-2'
                              >
                                <Button
                                  variant='ghost'
                                  size='icon'
                                  className='h-6 w-6'
                                  onClick={() => {
                                    setFiles(
                                      files.filter((_, i) => i !== index)
                                    );
                                  }}
                                >
                                  <X size={14} />
                                </Button>
                                {file.name}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <div className='flex justify-end mt-4'>
                        <Button type='submit'>确认上传</Button>
                      </div>
                    </div>
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
