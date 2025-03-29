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
  const [choicesString, setChoicesString] = useState<string>(''); // 用于存储逗号分隔的选项字符串
  const [choices, setChoices] = useState<string[]>([]);
  const [dfAlias, setDfAlias] = useState<string>('');
  const [dfColumn, setDfColumn] = useState<string>('');
  const [level, setLevel] = useState<number>(0);

  // UI状态
  const [openDataSourceAlias, setOpenDataSourceAlias] = useState(false);

  // 是否是级联类型
  const isCascadeType =
    paramTypeValue === 'cascade_single' ||
    paramTypeValue === 'cascade_multiple';

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
      setChoicesString(paramType.choices.join(','));

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
      setChoicesString('');
      setDfAlias('');
      setDfColumn('');
      setLevel(0);
    }
  }, [param, isOpen]);

  // 处理选项字符串变化
  const handleChoicesChange = (value: string) => {
    setChoicesString(value);
    const newChoices = value
      .split(',')
      .map((choice) => choice.trim())
      .filter((choice) => choice.length > 0);

    setChoices(newChoices);

    // 如果默认值不在选项列表中，则清空默认值
    if (defaultValue && !newChoices.includes(defaultValue)) {
      setDefaultValue('');
    }

    // 过滤掉不在选项列表中的默认值
    if (defaultValues.length > 0) {
      setDefaultValues(defaultValues.filter((v) => newChoices.includes(v)));
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

      // 非级联类型需要校验选项
      if (!isCascadeType && choices.length === 0) {
        toast.error('请至少添加一个选项');
        return;
      }

      // 级联类型需要校验数据源和列名
      if (isCascadeType && (!dfAlias || !dfColumn)) {
        toast.error('级联参数需要指定数据源和列名');
        return;
      }

      // 根据级联类型，设置默认选项
      let finalChoices = isCascadeType ? [] : choices;

      // 验证默认值
      if (
        paramTypeValue === 'plain_single' ||
        paramTypeValue === 'cascade_single'
      ) {
        if (!defaultValue && !isCascadeType && choices.length > 0) {
          setDefaultValue(choices[0]); // 自动选择第一个
        }
      } else {
        if (
          defaultValues.length === 0 &&
          !isCascadeType &&
          choices.length > 0
        ) {
          setDefaultValues([choices[0]]); // 自动选择第一个
        }
      }

      // 构建参数类型
      let paramType;
      if (paramTypeValue === 'plain_single') {
        paramType = {
          type: 'plain_single',
          default: defaultValue || (choices.length > 0 ? choices[0] : ''),
          choices: finalChoices,
        };
      } else if (paramTypeValue === 'plain_multiple') {
        paramType = {
          type: 'plain_multiple',
          default:
            defaultValues.length > 0
              ? defaultValues
              : choices.length > 0
                ? [choices[0]]
                : [],
          choices: finalChoices,
          dfAlias: dfAlias,
          dfColumn: dfColumn,
        };
      } else if (paramTypeValue === 'cascade_single') {
        paramType = {
          type: 'cascade_single',
          default: defaultValue || '',
          choices: finalChoices,
          dfAlias: dfAlias,
          dfColumn: dfColumn,
          level: level,
        };
      } else {
        paramType = {
          type: 'cascade_multiple',
          default: defaultValues.length > 0 ? defaultValues : [],
          choices: finalChoices,
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

          {/* 仅非级联类型显示选项和默认值 */}
          {!isCascadeType && (
            <>
              {/* 选项列表 - 使用逗号分隔的输入框 */}
              <div className='grid grid-cols-4 items-center gap-4'>
                <Label htmlFor='choices' className='text-right'>
                  选项列表*
                </Label>
                <Input
                  id='choices'
                  value={choicesString}
                  onChange={(e) => handleChoicesChange(e.target.value)}
                  className='col-span-3'
                  placeholder='逗号分隔的选项，如：选项1,选项2,选项3'
                />
              </div>

              {/* 默认值 - 单选类型 */}
              {paramTypeValue === 'plain_single' && (
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
              {paramTypeValue === 'plain_multiple' && (
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
            </>
          )}

          {/* 数据源相关字段 - 对所有非plain_single类型或级联类型都显示 */}
          {(paramTypeValue !== 'plain_single' || isCascadeType) && (
            <>
              <div className='grid grid-cols-4 items-center gap-4'>
                <Label htmlFor='dfAlias' className='text-right'>
                  数据源别名{isCascadeType ? '*' : ''}
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
                  数据列名{isCascadeType ? '*' : ''}
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
          {isCascadeType && (
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='level' className='text-right'>
                级联级别*
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

          {/* 级联类型说明 */}
          {isCascadeType && (
            <div className='grid grid-cols-4 items-start gap-4'>
              <div className='col-start-2 col-span-3 text-sm text-gray-500 bg-gray-50 p-2 rounded-md'>
                注意：级联参数的选项和默认值将从数据源中自动推断，无需手动设置。
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            取消
          </Button>
          <Button
            onClick={handleSaveParam}
            disabled={
              !name ||
              (!isCascadeType && choices.length === 0) ||
              (isCascadeType && (!dfAlias || !dfColumn))
            }
          >
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default EditArtifactParamModal;
