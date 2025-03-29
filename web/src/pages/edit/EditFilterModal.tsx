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
import { Textarea } from '@/components/ui/textarea'; // 假设需要 Textarea
import type {
  Parameter,
  SingleSelectParamConfig,
  MultiSelectParamConfig,
  DatePickerParamConfig,
  MultiInputParamConfig,
  SingleInputParamConfig,
} from '@/types/models/parameter';

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

  // 各种类型参数的配置状态 (根据需要添加/调整)
  const [singleSelectChoices, setSingleSelectChoices] = useState<string[]>([]);
  const [singleSelectDefault, setSingleSelectDefault] = useState('');
  const [singleInputDefault, setSingleInputDefault] = useState('');
  // ... 其他类型参数的状态 ...

  // --- 效果钩子 ---
  // 当 parameter prop 变化时 (打开模态框编辑现有参数)，填充表单
  useEffect(() => {
    if (parameter) {
      setName(parameter.name);
      setAlias(parameter.alias || '');
      setDescription(parameter.description || '');
      setParamType(parameter.paramConfig.type);

      // 根据类型填充特定配置
      switch (parameter.paramConfig.type) {
        case 'single_select':
          setSingleSelectChoices(parameter.paramConfig.choices);
          setSingleSelectDefault(parameter.paramConfig.default);
          break;
        case 'single_input':
          setSingleInputDefault(parameter.paramConfig.default);
          break;
        // ... 处理其他类型 ...
        default:
          // 处理未知类型或重置为默认值
          setSingleSelectChoices([]);
          setSingleSelectDefault('');
          setSingleInputDefault('');
          break;
      }
    } else {
      // 新增模式，重置表单
      setName('');
      setAlias('');
      setDescription('');
      setParamType('single_input'); // 重置为默认类型
      setSingleSelectChoices([]);
      setSingleSelectDefault('');
      setSingleInputDefault('');
      // ... 重置其他类型状态 ...
    }
  }, [parameter, isOpen]); // 依赖 isOpen 确保每次打开模态框都重新初始化

  // --- 事件处理 ---
  const handleSaveClick = () => {
    // 构建 paramConfig 对象
    let paramConfig: Parameter['paramConfig'];
    switch (paramType) {
      case 'single_select':
        paramConfig = {
          type: 'single_select',
          choices: singleSelectChoices,
          default: singleSelectDefault,
        };
        break;
      case 'single_input':
        paramConfig = { type: 'single_input', default: singleInputDefault };
        break;
      // ... 构建其他类型的 paramConfig ...
      case 'multi_select':
        // 示例，需要添加对应的状态和输入字段
        paramConfig = {
          type: 'multi_select',
          choices: [],
          default: [],
          sep: ',',
          wrapper: "'",
        };
        break;
      case 'date_picker':
        // 示例，需要添加对应的状态和输入字段
        paramConfig = {
          type: 'date_picker',
          dateFormat: 'YYYY-MM-DD',
          default: '',
        };
        break;
      case 'multi_input':
        // 示例，需要添加对应的状态和输入字段
        paramConfig = {
          type: 'multi_input',
          default: [],
          sep: ',',
          wrapper: "'",
        };
        break;
      default:
        // 不应该发生，但作为保险
        console.error('Unknown parameter type:', paramType);
        return;
    }

    const savedParameter: Parameter = {
      id: parameter?.id || generateId(), // 如果是编辑则用旧 ID，新增则生成新 ID
      name,
      alias: alias || undefined, // 如果为空则设为 undefined
      description: description || undefined, // 如果为空则设为 undefined
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
            <div className='grid gap-2'>
              <Label htmlFor='single-select-choices'>选项 (逗号分隔)</Label>
              <Input
                id='single-select-choices'
                value={singleSelectChoices.join(',')}
                onChange={(e) =>
                  setSingleSelectChoices(
                    e.target.value
                      .split(',')
                      .map((s) => s.trim())
                      .filter(Boolean)
                  )
                }
                placeholder='选项1,选项2,选项3'
              />
            </div>
            <div className='grid gap-2'>
              <Label htmlFor='single-select-default'>默认值</Label>
              <Select
                value={singleSelectDefault}
                onValueChange={setSingleSelectDefault}
              >
                <SelectTrigger id='single-select-default'>
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
          <div className='grid gap-2'>
            <Label htmlFor='single-input-default'>默认值</Label>
            <Input
              id='single-input-default'
              value={singleInputDefault}
              onChange={(e) => setSingleInputDefault(e.target.value)}
            />
          </div>
        );
      // ... 添加其他类型的字段渲染 ...
      case 'multi_select':
      case 'date_picker':
      case 'multi_input':
        return (
          <p className='text-sm text-muted-foreground'>
            类型 "{paramType}" 的配置界面待实现。
          </p>
        );
      default:
        return null;
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
