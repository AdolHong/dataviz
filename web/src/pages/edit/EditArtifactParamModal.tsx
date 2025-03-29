import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Check, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import type { ArtifactParam, DataSource } from '@/types';

interface EditArtifactParamModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (param: ArtifactParam) => void;
  param: ArtifactParam | null; // null表示新增
  dataSources: DataSource[];
}

// 辅助函数生成唯一ID
const generateId = () =>
  `param_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;

const EditArtifactParamModal = ({
  isOpen,
  onClose,
  onSave,
  param,
  dataSources,
}: EditArtifactParamModalProps) => {
  // 基本信息
  const [id, setId] = useState('');
  const [name, setName] = useState('');
  const [alias, setAlias] = useState('');
  const [description, setDescription] = useState('');
  const [valueType, setValueType] = useState<
    'string' | 'double' | 'boolean' | 'int'
  >('string');

  // 参数类型相关
  const [paramTypeValue, setParamTypeValue] = useState<
    'plain_single' | 'plain_multiple' | 'cascade_single' | 'cascade_multiple'
  >('plain_single');

  // 各参数类型的具体值
  const [defaultValue, setDefaultValue] = useState<string>('');
  const [defaultValues, setDefaultValues] = useState<string[]>([]);
  const [choices, setChoices] = useState<string[]>([]);
  const [dfAlias, setDfAlias] = useState<string>('');
  const [dfColumn, setDfColumn] = useState<string>('');
  const [level, setLevel] = useState<number>(0);

  // UI状态
  const [newChoice, setNewChoice] = useState<string>('');
  const [openDataSourceAlias, setOpenDataSourceAlias] = useState(false);

  // 初始化表单
  useEffect(() => {
    if (param) {
      // 编辑模式：填充数据
      setId(param.id);
      setName(param.name);
      setAlias(param.alias || '');
      setDescription(param.description || '');
      setValueType(param.valueType);
      setParamTypeValue(param.paramType.type);

      // 根据不同类型设置对应参数
      const paramType = param.paramType;
      setChoices(paramType.choices);

      if (
        paramType.type === 'plain_single' ||
        paramType.type === 'cascade_single'
      ) {
        setDefaultValue(paramType.default);
      } else if (
        paramType.type === 'plain_multiple' ||
        paramType.type === 'cascade_multiple'
      ) {
        setDefaultValues(paramType.default);
      }

      if (
        paramType.type === 'plain_multiple' ||
        paramType.type === 'cascade_multiple' ||
        paramType.type === 'cascade_single'
      ) {
        setDfAlias(paramType.dfAlias || '');
        setDfColumn(paramType.dfColumn || '');
      }

      if (
        paramType.type === 'cascade_single' ||
        paramType.type === 'cascade_multiple'
      ) {
        setLevel(paramType.level || 0);
      }
    } else {
      // 新增模式：重置所有
      setId(generateId());
      setName('');
      setAlias('');
      setDescription('');
      setValueType('string');
      setParamTypeValue('plain_single');
      setDefaultValue('');
      setDefaultValues([]);
      setChoices([]);
      setDfAlias('');
      setDfColumn('');
      setLevel(0);
    }
  }, [param, isOpen]);

  // 添加选项
  const handleAddChoice = () => {
    if (newChoice.trim() && !choices.includes(newChoice.trim())) {
      setChoices([...choices, newChoice.trim()]);
      setNewChoice('');
    }
  };

  // 移除选项
  const handleRemoveChoice = (choice: string) => {
    setChoices(choices.filter((c) => c !== choice));
    // 如果删除的是默认选项，也要移除默认值
    if (defaultValue === choice) {
      setDefaultValue('');
    }
    if (defaultValues.includes(choice)) {
      setDefaultValues(defaultValues.filter((v) => v !== choice));
    }
  };

  // 保存参数
  const handleSaveParam = () => {
    try {
      // 基本验证
      if (!name.trim()) {
        toast.error('参数名称不能为空');
        return;
      }

      if (choices.length === 0) {
        toast.error('请至少添加一个选项');
        return;
      }

      // 验证默认值
      if (
        paramTypeValue === 'plain_single' ||
        paramTypeValue === 'cascade_single'
      ) {
        if (!defaultValue && choices.length > 0) {
          setDefaultValue(choices[0]); // 自动选择第一个
        }
      } else {
        if (defaultValues.length === 0 && choices.length > 0) {
          setDefaultValues([choices[0]]); // 自动选择第一个
        }
      }

      // 构建参数类型
      let paramType;
      if (paramTypeValue === 'plain_single') {
        paramType = {
          type: 'plain_single',
          default: defaultValue || choices[0],
          choices: choices,
        };
      } else if (paramTypeValue === 'plain_multiple') {
        paramType = {
          type: 'plain_multiple',
          default: defaultValues.length > 0 ? defaultValues : [choices[0]],
          choices: choices,
          dfAlias: dfAlias,
          dfColumn: dfColumn,
        };
      } else if (paramTypeValue === 'cascade_single') {
        paramType = {
          type: 'cascade_single',
          default: defaultValue || choices[0],
          choices: choices,
          dfAlias: dfAlias,
          dfColumn: dfColumn,
          level: level,
        };
      } else {
        paramType = {
          type: 'cascade_multiple',
          default: defaultValues.length > 0 ? defaultValues : [choices[0]],
          choices: choices,
          dfAlias: dfAlias,
          dfColumn: dfColumn,
          level: level,
        };
      }

      // 构建最终参数对象
      const savedParam: ArtifactParam = {
        id: param?.id || id,
        name,
        alias: alias || undefined,
        description: description || undefined,
        valueType,
        paramType,
      };

      onSave(savedParam);
    } catch (error) {
      console.error('Error saving parameter:', error);
      toast.error('保存参数时发生错误');
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className='sm:max-w-[600px]'>
        <DialogHeader>
          <DialogTitle>{param ? '编辑参数' : '添加参数'}</DialogTitle>
        </DialogHeader>

        <div className='grid gap-4 py-4'>
          {/* 基本信息部分 */}
          <div className='grid grid-cols-4 items-center gap-4'>
            <Label htmlFor='name' className='text-right'>
              参数名称*
            </Label>
            <Input
              id='name'
              value={name}
              onChange={(e) => setName(e.target.value)}
              className='col-span-3'
              required
              placeholder='参数代码中的名称'
            />
          </div>

          <div className='grid grid-cols-4 items-center gap-4'>
            <Label htmlFor='alias' className='text-right'>
              参数别名
            </Label>
            <Input
              id='alias'
              value={alias}
              onChange={(e) => setAlias(e.target.value)}
              className='col-span-3'
              placeholder='参数的显示名称（可选）'
            />
          </div>

          <div className='grid grid-cols-4 items-center gap-4'>
            <Label htmlFor='description' className='text-right'>
              描述
            </Label>
            <Input
              id='description'
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className='col-span-3'
              placeholder='参数描述（可选）'
            />
          </div>

          <div className='grid grid-cols-4 items-center gap-4'>
            <Label htmlFor='valueType' className='text-right'>
              数据类型*
            </Label>
            <Select
              value={valueType}
              onValueChange={(value) => setValueType(value as any)}
            >
              <SelectTrigger className='col-span-3'>
                <SelectValue placeholder='选择数据类型' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='string'>字符串 (String)</SelectItem>
                <SelectItem value='double'>浮点数 (Double)</SelectItem>
                <SelectItem value='int'>整数 (Int)</SelectItem>
                <SelectItem value='boolean'>布尔值 (Boolean)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className='grid grid-cols-4 items-center gap-4'>
            <Label htmlFor='paramType' className='text-right'>
              参数类型*
            </Label>
            <Select
              value={paramTypeValue}
              onValueChange={(value) => setParamTypeValue(value as any)}
            >
              <SelectTrigger className='col-span-3'>
                <SelectValue placeholder='选择参数类型' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='plain_single'>
                  单选 (Plain Single)
                </SelectItem>
                <SelectItem value='plain_multiple'>
                  多选 (Plain Multiple)
                </SelectItem>
                <SelectItem value='cascade_single'>
                  级联单选 (Cascade Single)
                </SelectItem>
                <SelectItem value='cascade_multiple'>
                  级联多选 (Cascade Multiple)
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* 选项列表 */}
          <div className='grid grid-cols-4 items-start gap-4'>
            <Label className='text-right pt-2'>选项列表*</Label>
            <div className='col-span-3 space-y-2'>
              <div className='flex gap-2'>
                <Input
                  value={newChoice}
                  onChange={(e) => setNewChoice(e.target.value)}
                  placeholder='添加选项'
                  className='flex-1'
                />
                <Button type='button' onClick={handleAddChoice} size='sm'>
                  添加
                </Button>
              </div>

              <div className='max-h-32 overflow-y-auto border rounded-md p-2'>
                {choices.length > 0 ? (
                  <ul className='space-y-1'>
                    {choices.map((choice, index) => (
                      <li
                        key={index}
                        className='flex justify-between items-center text-sm p-1 hover:bg-gray-100 rounded'
                      >
                        <span>{choice}</span>
                        <Button
                          variant='ghost'
                          size='sm'
                          className='h-6 w-6 text-destructive'
                          onClick={() => handleRemoveChoice(choice)}
                        >
                          ×
                        </Button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className='text-center text-gray-500 py-2'>暂无选项</div>
                )}
              </div>
            </div>
          </div>

          {/* 默认值 - 单选类型 */}
          {(paramTypeValue === 'plain_single' ||
            paramTypeValue === 'cascade_single') && (
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='defaultValue' className='text-right'>
                默认值
              </Label>
              <Select
                value={defaultValue}
                onValueChange={setDefaultValue}
                disabled={choices.length === 0}
              >
                <SelectTrigger className='col-span-3'>
                  <SelectValue placeholder='选择默认值' />
                </SelectTrigger>
                <SelectContent>
                  {choices.map((choice, index) => (
                    <SelectItem key={index} value={choice}>
                      {choice}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* 默认值 - 多选类型 */}
          {(paramTypeValue === 'plain_multiple' ||
            paramTypeValue === 'cascade_multiple') && (
            <div className='grid grid-cols-4 items-start gap-4'>
              <Label className='text-right pt-2'>默认值</Label>
              <div className='col-span-3'>
                {choices.map((choice, index) => (
                  <div key={index} className='flex items-center mb-1'>
                    <input
                      type='checkbox'
                      id={`choice-${index}`}
                      checked={defaultValues.includes(choice)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setDefaultValues([...defaultValues, choice]);
                        } else {
                          setDefaultValues(
                            defaultValues.filter((v) => v !== choice)
                          );
                        }
                      }}
                      className='mr-2'
                    />
                    <label htmlFor={`choice-${index}`} className='text-sm'>
                      {choice}
                    </label>
                  </div>
                ))}
                {choices.length === 0 && (
                  <div className='text-gray-500 text-sm'>请先添加选项</div>
                )}
              </div>
            </div>
          )}

          {/* 数据源相关字段 */}
          {paramTypeValue !== 'plain_single' && (
            <>
              <div className='grid grid-cols-4 items-center gap-4'>
                <Label htmlFor='dfAlias' className='text-right'>
                  数据源别名
                </Label>
                <div className='col-span-3'>
                  <Popover
                    open={openDataSourceAlias}
                    onOpenChange={setOpenDataSourceAlias}
                  >
                    <PopoverTrigger asChild>
                      <Button
                        variant='outline'
                        role='combobox'
                        aria-expanded={openDataSourceAlias}
                        className='w-full justify-between'
                      >
                        {dfAlias || '选择数据源别名'}
                        <ChevronsUpDown className='ml-2 h-4 w-4 shrink-0 opacity-50' />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className='w-full p-0'>
                      <Command>
                        <CommandInput placeholder='搜索数据源...' />
                        <CommandList>
                          <CommandEmpty>没有找到匹配的数据源</CommandEmpty>
                          <CommandGroup>
                            {dataSources.map((ds) => (
                              <CommandItem
                                key={ds.alias}
                                value={ds.alias}
                                onSelect={(value) => {
                                  setDfAlias(value);
                                  setOpenDataSourceAlias(false);
                                }}
                              >
                                <Check
                                  className={cn(
                                    'mr-2 h-4 w-4',
                                    dfAlias === ds.alias
                                      ? 'opacity-100'
                                      : 'opacity-0'
                                  )}
                                />
                                {ds.alias}
                              </CommandItem>
                            ))}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                </div>
              </div>

              <div className='grid grid-cols-4 items-center gap-4'>
                <Label htmlFor='dfColumn' className='text-right'>
                  数据列名
                </Label>
                <Input
                  id='dfColumn'
                  value={dfColumn}
                  onChange={(e) => setDfColumn(e.target.value)}
                  className='col-span-3'
                  placeholder='数据中的列名'
                />
              </div>
            </>
          )}

          {/* 级联参数的级别 */}
          {(paramTypeValue === 'cascade_single' ||
            paramTypeValue === 'cascade_multiple') && (
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='level' className='text-right'>
                级联级别
              </Label>
              <Input
                id='level'
                type='number'
                min='0'
                value={level}
                onChange={(e) => setLevel(parseInt(e.target.value) || 0)}
                className='col-span-3'
                placeholder='级联层级（0表示顶层）'
              />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            取消
          </Button>
          <Button
            onClick={handleSaveParam}
            disabled={!name || choices.length === 0}
          >
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default EditArtifactParamModal;
