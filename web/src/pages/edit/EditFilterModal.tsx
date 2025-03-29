import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox'; // 添加 Checkbox 组件导入
import type {
  Parameter,
  SingleSelectParamConfig,
  MultiSelectParamConfig,
  DatePickerParamConfig,
  MultiInputParamConfig,
  SingleInputParamConfig,
} from '@/types/models/parameter';
import { toast } from 'sonner';

interface EditFilterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (parameter: Parameter) => void;
  parameter: Parameter | null; // 接收要编辑的参数，null 表示新增
}

// 辅助函数生成唯一 ID (实际项目中可能使用 uuid 库)
const generateId = () =>
  `p_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;

const EditFilterModal = ({
  isOpen,
  onClose,
  onSave,
  parameter,
}: EditFilterModalProps) => {
  // --- 表单状态 ---
  const [name, setName] = useState('');
  const [alias, setAlias] = useState('');
  const [description, setDescription] = useState('');
  const [paramType, setParamType] =
    useState<Parameter['paramConfig']['type']>('single_input'); // 默认类型

  // --- 各类型参数配置状态 ---
  // single_select
  const [singleSelectChoicesJoined, setSingleSelectChoicesJoined] =
    useState<string>('');
  const [singleSelectChoices, setSingleSelectChoices] = useState<string[]>([]);
  const [singleSelectDefault, setSingleSelectDefault] = useState('');
  // single_input
  const [singleInputDefault, setSingleInputDefault] = useState('');
  // multi_select
  const [multiSelectChoicesJoined, setMultiSelectChoicesJoined] =
    useState<string>('');
  const [multiSelectChoices, setMultiSelectChoices] = useState<string[]>([]);
  const [multiSelectDefault, setMultiSelectDefault] = useState<string[]>([]);
  const [multiSelectSep, setMultiSelectSep] = useState(',');
  const [multiSelectWrapper, setMultiSelectWrapper] = useState("'");
  // date_picker
  const [datePickerFormat, setDatePickerFormat] = useState('YYYY-MM-DD');
  const [datePickerDefault, setDatePickerDefault] = useState('');
  // multi_input
  const [multiInputDefault, setMultiInputDefault] = useState<string[]>([]);
  const [multiInputSep, setMultiInputSep] = useState(',');
  const [multiInputWrapper, setMultiInputWrapper] = useState("'");

  // --- 效果钩子 ---
  useEffect(() => {
    // 重置所有特定配置状态的函数
    const resetConfigStates = () => {
      setSingleSelectChoicesJoined('');
      setMultiSelectChoicesJoined('');
      setSingleSelectChoices([]);
      setSingleSelectDefault('');
      setSingleInputDefault('');
      setMultiSelectChoices([]);
      setMultiSelectDefault([]);
      setMultiSelectSep(',');
      setMultiSelectWrapper("'");
      setDatePickerFormat('YYYY-MM-DD');
      setDatePickerDefault('');
      setMultiInputDefault([]);
      setMultiInputSep(',');
      setMultiInputWrapper("'");
    };

    if (parameter) {
      setName(parameter.name);
      setAlias(parameter.alias || '');
      setDescription(parameter.description || '');
      setParamType(parameter.paramConfig.type);
      resetConfigStates(); // 先重置所有特定配置状态

      // 根据类型填充特定配置
      switch (parameter.paramConfig.type) {
        case 'single_select':
          setSingleSelectChoicesJoined(parameter.paramConfig.choices.join(','));
          setSingleSelectChoices(parameter.paramConfig.choices);
          setSingleSelectDefault(parameter.paramConfig.default);
          break;
        case 'multi_select':
          setMultiSelectChoicesJoined(parameter.paramConfig.choices.join(','));
          setMultiSelectChoices(parameter.paramConfig.choices);
          setMultiSelectDefault(parameter.paramConfig.default);
          setMultiSelectSep(parameter.paramConfig.sep);
          setMultiSelectWrapper(parameter.paramConfig.wrapper);
          break;
        case 'single_input':
          setSingleInputDefault(parameter.paramConfig.default);
          break;
        case 'multi_input':
          setMultiInputDefault(parameter.paramConfig.default);
          setMultiInputSep(parameter.paramConfig.sep);
          setMultiInputWrapper(parameter.paramConfig.wrapper);
          break;
        case 'date_picker':
          setDatePickerFormat(parameter.paramConfig.dateFormat);
          setDatePickerDefault(parameter.paramConfig.default);
          break;
        default:
          toast.error('[DEBUG] parameter edit: 未知参数类型');
          // 在类型不匹配时，已由 resetConfigStates 处理
          break;
      }
    } else {
      // 新增模式，重置所有状态
      setName('');
      setAlias('');
      setDescription('');
      setParamType('single_input'); // 重置为默认类型
      resetConfigStates(); // 重置所有特定配置状态
    }
  }, [parameter, isOpen]);

  // --- 事件处理 ---
  const handleSaveClick = () => {
    let paramConfig: Parameter['paramConfig'];
    try {
      switch (paramType) {
        case 'single_select':
          paramConfig = {
            type: 'single_select',
            choices: singleSelectChoices,
            default: singleSelectDefault,
          };
          // 校验：默认值必须在选项中
          if (
            singleSelectDefault &&
            !singleSelectChoices.includes(singleSelectDefault)
          ) {
            console.warn(
              'Single select default value not in choices. Resetting default.'
            );
            paramConfig.default = singleSelectChoices[0] || ''; // or handle as error
          }
          break;
        case 'single_input':
          paramConfig = { type: 'single_input', default: singleInputDefault };
          break;
        case 'multi_select':
          paramConfig = {
            type: 'multi_select',
            choices: multiSelectChoices,
            default: multiSelectDefault,
            sep: multiSelectSep,
            wrapper: multiSelectWrapper,
          };
          // 校验：默认值数组中的每个值都必须在选项中
          const validMultiDefaults = multiSelectDefault.filter((d) =>
            multiSelectChoices.includes(d)
          );
          if (validMultiDefaults.length !== multiSelectDefault.length) {
            console.warn(
              'Some multi select default values were not in choices. Keeping only valid ones.'
            );
            paramConfig.default = validMultiDefaults; // or handle as error
          }
          break;
        case 'date_picker':
          paramConfig = {
            type: 'date_picker',
            dateFormat: datePickerFormat,
            default: datePickerDefault,
          };
          // 可以添加日期格式校验
          break;
        case 'multi_input':
          paramConfig = {
            type: 'multi_input',
            default: multiInputDefault,
            sep: multiInputSep,
            wrapper: multiInputWrapper,
          };
          break;
        default:
          // 利用 never 类型检查确保所有 case 都已处理 (编译时检查)
          const exhaustiveCheck: never = paramType;
          console.error('Unhandled parameter type:', exhaustiveCheck);
          return; // 或者抛出错误
      }
    } catch (error) {
      console.error('Error constructing paramConfig:', error);
      // 可能需要向用户显示错误消息
      return;
    }

    const savedParameter: Parameter = {
      id: parameter?.id || generateId(),
      name,
      alias: alias || undefined,
      description: description || undefined,
      paramConfig,
    };
    onSave(savedParameter);
  };

  // 渲染特定类型的配置字段
  const renderParamConfigFields = () => {
    switch (paramType) {
      case 'single_select':
        return (
          <>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='single-select-choices' className='text-right'>
                选项
              </Label>
              <Input
                id='single-select-choices'
                value={singleSelectChoicesJoined}
                onChange={(e) => {
                  setSingleSelectChoicesJoined(e.target.value);
                  const choices = e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean);
                  setSingleSelectChoices(choices);
                }}
                className='col-span-3'
                placeholder='逗号分隔, e.g. 选项1,选项2'
              />
            </div>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='single-select-default' className='text-right'>
                默认值
              </Label>
              <Select
                value={singleSelectDefault}
                onValueChange={setSingleSelectDefault}
                disabled={singleSelectChoices.length === 0}
              >
                <SelectTrigger
                  id='single-select-default'
                  className='col-span-3'
                >
                  <SelectValue placeholder='选择默认值' />
                </SelectTrigger>
                <SelectContent>
                  {singleSelectChoices.map((choice) => (
                    <SelectItem key={choice} value={choice}>
                      {choice}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </>
        );
      case 'single_input':
        return (
          <div className='grid grid-cols-4 items-center gap-4'>
            <Label htmlFor='single-input-default' className='text-right'>
              默认值
            </Label>
            <Input
              id='single-input-default'
              value={singleInputDefault}
              onChange={(e) => setSingleInputDefault(e.target.value)}
              className='col-span-3'
            />
          </div>
        );
      case 'multi_select':
        return (
          <>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='multi-select-choices' className='text-right'>
                选项
              </Label>
              <Input
                id='multi-select-choices'
                value={multiSelectChoicesJoined}
                onChange={(e) => {
                  setMultiSelectChoicesJoined(e.target.value);
                  const choices = e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean);
                  setMultiSelectChoices(choices);
                }}
                className='col-span-3'
                placeholder='逗号分隔, e.g. 选项A,选项B'
              />
            </div>
            <div className='grid grid-cols-4 items-start gap-4'>
              <Label className='text-right pt-2'>默认值</Label>
              <div className='col-span-3 space-y-2'>
                {multiSelectChoices.length > 0 ? (
                  multiSelectChoices.map((choice) => (
                    <div key={choice} className='flex items-center space-x-2'>
                      <Checkbox
                        id={`choice-${choice}`}
                        checked={multiSelectDefault.includes(choice)}
                        onCheckedChange={(checked) => {
                          if (checked) {
                            setMultiSelectDefault([
                              ...multiSelectDefault,
                              choice,
                            ]);
                          } else {
                            setMultiSelectDefault(
                              multiSelectDefault.filter((c) => c !== choice)
                            );
                          }
                        }}
                      />
                      <Label
                        htmlFor={`choice-${choice}`}
                        className='text-sm font-normal'
                      >
                        {choice}
                      </Label>
                    </div>
                  ))
                ) : (
                  <p className='text-sm text-muted-foreground'>请先添加选项</p>
                )}
              </div>
            </div>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='multi-select-sep' className='text-right'>
                分隔符
              </Label>
              <Input
                id='multi-select-sep'
                value={multiSelectSep}
                onChange={(e) => setMultiSelectSep(e.target.value)}
                className='col-span-3'
              />
            </div>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='multi-select-wrapper' className='text-right'>
                包装符
              </Label>
              <Input
                id='multi-select-wrapper'
                value={multiSelectWrapper}
                onChange={(e) => setMultiSelectWrapper(e.target.value)}
                className='col-span-3'
                placeholder='e.g. &apos; or "'
              />
            </div>
          </>
        );
      case 'date_picker':
        return (
          <>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='date-picker-format' className='text-right'>
                日期格式
              </Label>
              <Input
                id='date-picker-format'
                value={datePickerFormat}
                onChange={(e) => setDatePickerFormat(e.target.value)}
                className='col-span-3'
                placeholder='e.g. YYYY-MM-DD'
              />
            </div>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='date-picker-default' className='text-right'>
                默认日期
              </Label>
              {/* TODO: Implement a proper date picker component */}
              <Input
                id='date-picker-default'
                type='text' // Should ideally be a date picker input
                value={datePickerDefault}
                onChange={(e) => setDatePickerDefault(e.target.value)}
                className='col-span-3'
                placeholder='默认日期字符串'
              />
            </div>
          </>
        );
      case 'multi_input':
        return (
          <>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='multi-input-default' className='text-right'>
                默认值
              </Label>
              <Input
                id='multi-input-default'
                value={multiInputDefault.join(',')}
                onChange={(e) =>
                  setMultiInputDefault(
                    e.target.value
                      .split(',')
                      .map((s) => s.trim())
                      .filter(Boolean)
                  )
                }
                className='col-span-3'
                placeholder='逗号分隔默认值'
              />
            </div>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='multi-input-sep' className='text-right'>
                分隔符
              </Label>
              <Input
                id='multi-input-sep'
                value={multiInputSep}
                onChange={(e) => setMultiInputSep(e.target.value)}
                className='col-span-3'
              />
            </div>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='multi-input-wrapper' className='text-right'>
                包装符
              </Label>
              <Input
                id='multi-input-wrapper'
                value={multiInputWrapper}
                onChange={(e) => setMultiInputWrapper(e.target.value)}
                className='col-span-3'
                placeholder='e.g. &apos; or "'
              />
            </div>
          </>
        );
      default:
        // 利用 never 类型检查确保所有 case 都已处理 (编译时检查)
        const exhaustiveCheck: never = paramType;
        return (
          <p className='text-sm text-destructive'>
            未知参数类型: {exhaustiveCheck}
          </p>
        );
    }
  };

  // --- JSX ---
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className='sm:max-w-[525px]'>
        <DialogHeader>
          <DialogTitle>
            {parameter ? '编辑筛选条件' : '添加筛选条件'}
          </DialogTitle>
          <DialogDescription>
            配置筛选条件的名称、类型和具体设置。
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-4 py-4'>
          <div className='grid grid-cols-4 items-center gap-4'>
            <Label htmlFor='name' className='text-right'>
              名称*
            </Label>
            <Input
              id='name'
              value={name}
              onChange={(e) => setName(e.target.value)}
              className='col-span-3'
              required
            />
          </div>
          <div className='grid grid-cols-4 items-center gap-4'>
            <Label htmlFor='alias' className='text-right'>
              别名
            </Label>
            <Input
              id='alias'
              value={alias}
              onChange={(e) => setAlias(e.target.value)}
              className='col-span-3'
              placeholder='（可选）用户界面显示的名称'
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
              placeholder='（可选）解释参数用途'
            />
          </div>
          <div className='grid grid-cols-4 items-center gap-4'>
            <Label htmlFor='param-type' className='text-right'>
              类型*
            </Label>
            <Select
              value={paramType}
              onValueChange={(value: Parameter['paramConfig']['type']) =>
                setParamType(value)
              }
            >
              <SelectTrigger id='param-type' className='col-span-3'>
                <SelectValue placeholder='选择参数类型' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='single_input'>文本输入</SelectItem>
                <SelectItem value='multi_input'>多值输入</SelectItem>
                <SelectItem value='single_select'>单选列表</SelectItem>
                <SelectItem value='multi_select'>多选列表</SelectItem>
                <SelectItem value='date_picker'>日期选择</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* 动态渲染特定类型的配置 */}
          {renderParamConfigFields()}
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            取消
          </Button>
          <Button onClick={handleSaveClick} disabled={!name}>
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default EditFilterModal;
