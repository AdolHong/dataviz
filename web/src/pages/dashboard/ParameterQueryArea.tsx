import React, { useState } from 'react';
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
} from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';
import { Checkbox } from '@/components/ui/checkbox';
import { type Parameter } from '@/types/models/parameter';

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
            <div className='flex flex-col gap-2'>
              {param.config.choices.map((choice) => (
                <div key={choice} className='flex items-center space-x-2'>
                  <Checkbox
                    id={`${param.id}-${choice}`}
                    checked={values[param.id]?.includes(choice)}
                    onCheckedChange={(checked) => {
                      const currentValues = values[param.id] || [];
                      const newValues = checked
                        ? [...currentValues, choice]
                        : currentValues.filter((v: string) => v !== choice);
                      handleValueChange(param.id, newValues);
                    }}
                  />
                  <label htmlFor={`${param.id}-${choice}`} className='text-sm'>
                    {choice}
                  </label>
                </div>
              ))}
            </div>
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
          return (
            <div className='space-y-2'>
              {(values[param.id] || param.config.default).map(
                (value: string, index: number) => (
                  <div key={index} className='flex gap-2'>
                    <Input
                      value={value}
                      onChange={(e) => {
                        const newValues = [
                          ...(values[param.id] || param.config.default),
                        ];
                        newValues[index] = e.target.value;
                        handleValueChange(param.id, newValues);
                      }}
                    />
                    <Button
                      variant='outline'
                      size='icon'
                      onClick={() => {
                        const newValues = [
                          ...(values[param.id] || param.config.default),
                        ];
                        newValues.splice(index, 1);
                        handleValueChange(param.id, newValues);
                      }}
                    >
                      <X size={16} />
                    </Button>
                  </div>
                )
              )}
              <Button
                variant='outline'
                onClick={() => {
                  handleValueChange(param.id, [
                    ...(values[param.id] || param.config.default),
                    '',
                  ]);
                }}
              >
                <Plus size={16} className='mr-1' />
                添加
              </Button>
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
      <CardContent className='pt-6'>
        <form onSubmit={handleSubmit}>
          <div className='flex justify-between items-center mb-4'>
            <h3 className='text-sm font-medium'>查询参数</h3>
            <Button
              variant='ghost'
              size='sm'
              onClick={toggleParametersExpanded}
              className='h-8 px-2'
            >
              {parametersExpanded ? (
                <ChevronUp size={16} className='text-muted-foreground' />
              ) : (
                <ChevronDown size={16} className='text-muted-foreground' />
              )}
            </Button>
          </div>

          {parametersExpanded && (
            <div
              className={cn(
                'grid gap-4',
                requireFileUpload ? 'grid-cols-2' : 'grid-cols-3 md:grid-cols-4'
              )}
            >
              <div
                className={cn(
                  'space-y-4',
                  requireFileUpload ? 'col-span-1' : 'col-span-3 md:col-span-4'
                )}
              >
                <div className='grid grid-cols-1 md:grid-cols-3 gap-4'>
                  {parameters.map((param) => (
                    <div key={param.id}>{renderParameterInput(param)}</div>
                  ))}
                </div>
              </div>

              {requireFileUpload && (
                <div className='col-span-1 space-y-4'>
                  <div className='space-y-2'>
                    <Label htmlFor='file-upload'>上传文件</Label>
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
                        <p className='text-sm font-medium'>已选择的文件:</p>
                        <ul className='text-sm max-h-40 overflow-y-auto space-y-1'>
                          {files.map((file, index) => (
                            <li
                              key={index}
                              className='text-muted-foreground truncate'
                            >
                              {file.name}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className='mt-6 flex justify-end'>
            <Button type='submit'>查询</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
