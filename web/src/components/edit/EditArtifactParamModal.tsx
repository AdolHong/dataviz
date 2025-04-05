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
import { Combobox } from '@/components/combobox';
import { Plus, Trash2 } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { toast } from 'sonner';
import type {
  SinglePlainParam,
  MultiplePlainParam,
  CascaderParam,
  CascaderLevel,
} from '@/types';

// 定义参数编辑模态框属性
interface EditArtifactParamModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (
    param: SinglePlainParam | MultiplePlainParam | CascaderParam
  ) => void;
  paramData: { param: any; type: 'plain' | 'cascader'; id: string } | null; // null表示新增
  dependencies: string[];
  plainParamNames: string[];
  setPlainParamNames: (names: string[]) => void;
}

// 辅助函数生成唯一ID
const generateId = () =>
  `param_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;

const EditArtifactParamModal = ({
  isOpen,
  onClose,
  onSave,
  paramData,
  dependencies,
  plainParamNames,
  setPlainParamNames,
}: EditArtifactParamModalProps) => {
  // 参数类型选择
  const [paramType, setParamType] = useState<'plain' | 'cascader'>('plain');

  // Plain 参数的状态
  const [plainId, setPlainId] = useState('');
  const [plainName, setPlainName] = useState('');
  const [plainAlias, setPlainAlias] = useState('');
  const [plainDescription, setPlainDescription] = useState('');
  const [plainValueType, setPlainValueType] = useState<
    'string' | 'double' | 'boolean' | 'int'
  >('string');
  const [plainParamType, setPlainParamType] = useState<'single' | 'multiple'>(
    'single'
  );
  const [plainDefault, setPlainDefault] = useState<string>('');
  const [plainDefaultMultiple, setPlainDefaultMultiple] = useState<string[]>(
    []
  );
  const [plainChoices, setPlainChoices] = useState<Record<string, string>[]>(
    []
  );
  const [plainChoicesString, setPlainChoicesString] = useState('');

  // Cascader 参数的状态
  const [cascaderDfAlias, setCascaderDfAlias] = useState('');
  const [cascaderLevels, setCascaderLevels] = useState<CascaderLevel[]>([]);

  // 初始化表单
  useEffect(() => {
    if (paramData) {
      // 编辑模式
      setParamType(paramData.type);

      if (paramData.type === 'plain') {
        const param = paramData.param as SinglePlainParam | MultiplePlainParam;
        setPlainId(param.id);
        setPlainName(param.name);
        setPlainAlias(param.alias || '');
        setPlainDescription(param.description || '');
        setPlainValueType(param.valueType);
        setPlainParamType(param.type);
        setPlainChoices(param.choices);
        setPlainChoicesString(
          param.choices.map((choice) => `${choice.value}`).join(',')
        );

        if (param.type === 'single') {
          setPlainDefault(param.default);
        } else {
          setPlainDefaultMultiple(param.default);
        }
      } else {
        const param = paramData.param as CascaderParam;
        setCascaderDfAlias(param.dfAlias);
        setCascaderLevels([...param.levels]);
      }
    } else {
      // 新增模式：重置所有
      resetForm();
    }
  }, [paramData, isOpen]);

  // 重置表单
  const resetForm = () => {
    setParamType('plain');
    // Plain 参数重置
    setPlainId(generateId());
    setPlainName('');
    setPlainAlias('');
    setPlainDescription('');
    setPlainValueType('string');
    setPlainParamType('single');
    setPlainDefault('');
    setPlainDefaultMultiple([]);
    setPlainChoices([]);
    setPlainChoicesString('');
    // Cascader 参数重置
    setCascaderDfAlias('');
    setCascaderLevels([]);
  };

  // 处理选项字符串变化
  const handleChoicesChange = (value: string) => {
    setPlainChoicesString(value);
    const newChoices = value
      .split(',')
      .map((choice) => choice.trim())
      .filter((choice) => choice.length > 0);

    setPlainChoices(
      newChoices.map((choice) => ({
        key: choice,
        value: choice,
      }))
    );

    // 如果默认值不在选项列表中，则清空默认值
    if (plainDefault && !newChoices.includes(plainDefault)) {
      setPlainDefault('');
    }

    // 过滤掉不在选项列表中的默认值
    if (plainDefaultMultiple.length > 0) {
      setPlainDefaultMultiple(
        plainDefaultMultiple.filter((v) => newChoices.includes(v))
      );
    }
  };

  // 添加级联级别
  const handleAddCascaderLevel = () => {
    setCascaderLevels([
      ...cascaderLevels,
      { dfColumn: '', name: `级别 ${cascaderLevels.length}` },
    ]);
  };

  // 更新级联级别
  const handleUpdateCascaderLevel = (
    index: number,
    field: keyof CascaderLevel,
    value: string
  ) => {
    const newLevels = [...cascaderLevels];
    newLevels[index] = { ...newLevels[index], [field]: value };
    setCascaderLevels(newLevels);
  };

  // 删除级联级别
  const handleDeleteCascaderLevel = (index: number) => {
    setCascaderLevels(cascaderLevels.filter((_, i) => i !== index));
  };

  // 保存参数
  const handleSaveParam = () => {
    try {
      if (paramType === 'plain') {
        // 基本验证
        if (!plainName.trim()) {
          toast.error('参数名称不能为空');
          return;
        }

        // 判断name中仅包含数字、字母、下划线, 首字符为字母
        if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(plainName)) {
          toast.error(
            '[PARAM] 异常, 名称仅包含数字、字母、下划线, 首字符为字母'
          );
          return;
        }

        if (plainName.startsWith('df_')) {
          toast.error('参数名称不能以df_开头');
          return;
        }

        // 检查是否存在同名参数
        if (
          plainParamNames.includes(plainName) &&
          plainName !== paramData?.param.name
        ) {
          toast.error('参数名称已存在');
          return;
        }

        if (plainChoices.length === 0) {
          toast.error('请至少添加一个选项');
          return;
        }

        if (plainParamType === 'single') {
          // 构建单选参数
          const singleParam: SinglePlainParam = {
            type: 'single',
            id: paramData?.type === 'plain' ? paramData.param.id : plainId,
            name: plainName,
            alias: plainAlias || undefined,
            description: plainDescription || undefined,
            valueType: plainValueType,
            default: plainDefault || plainChoices[0].value,
            choices: plainChoices,
          };
          onSave(singleParam);
        } else {
          // 构建多选参数
          const multipleParam: MultiplePlainParam = {
            type: 'multiple',
            id: paramData?.type === 'plain' ? paramData.param.id : plainId,
            name: plainName,
            alias: plainAlias || undefined,
            description: plainDescription || undefined,
            valueType: plainValueType,
            default:
              plainDefaultMultiple.length > 0
                ? plainDefaultMultiple
                : [plainChoices[0].value],
            choices: plainChoices,
          };
          onSave(multipleParam);
        }

        // todo: 删除旧名, 更换新名
        const newPlainParamNames = plainParamNames.filter(
          (name) => name !== paramData?.param.name
        );
        newPlainParamNames.push(plainName);
        setPlainParamNames(newPlainParamNames);
      } else {
        // Cascader 参数验证
        if (!cascaderDfAlias) {
          toast.error('数据源别名不能为空');
          return;
        }

        if (cascaderLevels.length === 0) {
          toast.error('请至少添加一个级联级别');
          return;
        }

        for (let i = 0; i < cascaderLevels.length; i++) {
          if (!cascaderLevels[i].dfColumn || !cascaderLevels[i].name) {
            toast.error(`级别 ${i + 1} 的数据列名和名称不能为空`);
            return;
          }
        }

        // 构建级联参数
        const cascaderParam: CascaderParam = {
          dfAlias: cascaderDfAlias,
          levels: cascaderLevels,
        };

        onSave(cascaderParam);
      }
    } catch (error) {
      console.error('Error saving parameter:', error);
      toast.error('保存参数时发生错误');
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className='sm:max-w-[600px]'>
        <DialogHeader>
          <DialogTitle>{paramData ? '编辑参数' : '添加参数'}</DialogTitle>
        </DialogHeader>

        <div className='grid gap-4 py-4'>
          {/* 参数类型选择 */}
          <div className='grid grid-cols-4 items-center gap-4'>
            <Label className='text-right'>参数类型*</Label>
            <RadioGroup
              value={paramType}
              onValueChange={(value) =>
                setParamType(value as 'plain' | 'cascader')
              }
              className='col-span-3 flex'
            >
              <div className='flex items-center space-x-2 mr-4'>
                <RadioGroupItem value='plain' id='param-type-plain' />
                <Label htmlFor='param-type-plain'>普通参数</Label>
              </div>
              <div className='flex items-center space-x-2'>
                <RadioGroupItem value='cascader' id='param-type-cascader' />
                <Label htmlFor='param-type-cascader'>级联参数</Label>
              </div>
            </RadioGroup>
          </div>

          {/* Plain 参数表单 */}
          {paramType === 'plain' && (
            <>
              <div className='grid grid-cols-4 items-center gap-4'>
                <Label htmlFor='plainName' className='text-right'>
                  参数名称*
                </Label>
                <Input
                  id='plainName'
                  value={plainName}
                  onChange={(e) => setPlainName(e.target.value)}
                  className='col-span-3'
                  required
                  placeholder='参数代码中的名称'
                />
              </div>

              <div className='grid grid-cols-4 items-center gap-4'>
                <Label htmlFor='plainAlias' className='text-right'>
                  参数别名
                </Label>
                <Input
                  id='plainAlias'
                  value={plainAlias}
                  onChange={(e) => setPlainAlias(e.target.value)}
                  className='col-span-3'
                  placeholder='参数的显示名称（可选）'
                />
              </div>

              <div className='grid grid-cols-4 items-center gap-4'>
                <Label htmlFor='plainDescription' className='text-right'>
                  描述
                </Label>
                <Input
                  id='plainDescription'
                  value={plainDescription}
                  onChange={(e) => setPlainDescription(e.target.value)}
                  className='col-span-3'
                  placeholder='参数描述（可选）'
                />
              </div>

              <div className='grid grid-cols-4 items-center gap-4'>
                <Label htmlFor='plainValueType' className='text-right'>
                  数据类型*
                </Label>
                <Select
                  value={plainValueType}
                  onValueChange={(value) => setPlainValueType(value as any)}
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
                <Label className='text-right'>参数值类型*</Label>
                <RadioGroup
                  value={plainParamType}
                  onValueChange={(value) =>
                    setPlainParamType(value as 'single' | 'multiple')
                  }
                  className='col-span-3 flex'
                >
                  <div className='flex items-center space-x-2 mr-4'>
                    <RadioGroupItem value='single' id='param-single' />
                    <Label htmlFor='param-single'>单选</Label>
                  </div>
                  <div className='flex items-center space-x-2'>
                    <RadioGroupItem value='multiple' id='param-multiple' />
                    <Label htmlFor='param-multiple'>多选</Label>
                  </div>
                </RadioGroup>
              </div>

              {/* 选项列表 - 使用逗号分隔的输入框 */}
              <div className='grid grid-cols-4 items-center gap-4'>
                <Label htmlFor='plainChoices' className='text-right'>
                  选项列表(逗号分隔)*
                </Label>
                <Input
                  id='plainChoices'
                  value={plainChoicesString}
                  onChange={(e) => handleChoicesChange(e.target.value)}
                  className='col-span-3'
                  placeholder='逗号分隔的选项，如：选项1,选项2,选项3'
                />
              </div>

              {/* 默认值 - 单选类型 */}
              {plainParamType === 'single' && (
                <div className='grid grid-cols-4 items-start gap-4'>
                  <Label htmlFor='plainDefault' className='text-right pt-2'>
                    默认值
                  </Label>
                  <div className='col-span-3'>
                    <Combobox
                      options={plainChoices.map((choice) => ({
                        key: choice.key,
                        value: choice.value,
                      }))}
                      value={plainDefault}
                      onValueChange={(value: string | string[]) => {
                        if (!Array.isArray(value)) {
                          setPlainDefault(plainDefault === value ? '' : value);
                        }
                      }}
                      mode='single'
                      placeholder='选择默认值'
                      disabled={plainChoices.length === 0}
                    />
                  </div>
                </div>
              )}

              {/* 默认值 - 多选类型 */}
              {plainParamType === 'multiple' && (
                <div className='grid grid-cols-4 items-start gap-4'>
                  <Label
                    htmlFor='plainDefaultMultiple'
                    className='text-right pt-2'
                  >
                    默认值
                  </Label>
                  <div className='col-span-3'>
                    <Combobox
                      options={plainChoices.map((choice) => ({
                        key: choice.key,
                        value: choice.value,
                      }))}
                      value={plainDefaultMultiple}
                      onValueChange={(value: string | string[]) => {
                        if (Array.isArray(value)) {
                          setPlainDefaultMultiple(value.sort());
                        }
                      }}
                      mode='multiple'
                      placeholder='选择默认值'
                      disabled={plainChoices.length === 0}
                    />
                    {plainChoices.length === 0 && (
                      <div className='text-gray-500 text-sm'>请先添加选项</div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          {/* Cascader 参数表单 */}
          {paramType === 'cascader' && (
            <>
              <div className='grid grid-cols-4 items-center gap-4'>
                <Label htmlFor='cascaderDfAlias' className='text-right'>
                  数据源别名*
                </Label>
                <div className='col-span-3'>
                  <Combobox
                    options={dependencies.map((dependency) => ({
                      key: dependency,
                      value: dependency,
                    }))}
                    value={cascaderDfAlias}
                    onValueChange={(value: string | string[]) => {
                      if (Array.isArray(value)) {
                        setCascaderDfAlias(value[0]);
                      } else {
                        setCascaderDfAlias(value);
                      }
                    }}
                    mode='single'
                    placeholder='选择数据源别名'
                  />
                </div>
              </div>

              <div className='grid grid-cols-4 items-start gap-4 mt-2'>
                <Label className='text-right pt-2'>级联层级列表*</Label>
                <div className='col-span-3 space-y-3'>
                  {cascaderLevels.length > 0 ? (
                    cascaderLevels.map((level, index) => (
                      <div
                        key={index}
                        className='border rounded-md p-3 relative group'
                      >
                        <h4 className='text-sm font-medium mb-2'>
                          级别 {index + 1}
                        </h4>

                        <div className='grid gap-2'>
                          <div className='grid grid-cols-4 items-center gap-2'>
                            <Label
                              htmlFor={`level-${index}-column`}
                              className='text-right text-xs'
                            >
                              数据列名*
                            </Label>
                            <Input
                              id={`level-${index}-column`}
                              value={level.dfColumn}
                              onChange={(e) =>
                                handleUpdateCascaderLevel(
                                  index,
                                  'dfColumn',
                                  e.target.value
                                )
                              }
                              className='col-span-3'
                              placeholder='指定df中的column'
                            />
                          </div>
                          <div className='grid grid-cols-4 items-center gap-2'>
                            <Label
                              htmlFor={`level-${index}-name`}
                              className='text-right text-xs'
                            >
                              名称*
                            </Label>
                            <Input
                              id={`level-${index}-name`}
                              value={level.name}
                              onChange={(e) =>
                                handleUpdateCascaderLevel(
                                  index,
                                  'name',
                                  e.target.value
                                )
                              }
                              className='col-span-3'
                              placeholder='名称, 便于理解'
                            />
                          </div>

                          <div className='grid grid-cols-4 items-center gap-2'>
                            <Label
                              htmlFor={`level-${index}-description`}
                              className='text-right text-xs'
                            >
                              描述
                            </Label>
                            <Input
                              id={`level-${index}-description`}
                              value={level.description || ''}
                              onChange={(e) =>
                                handleUpdateCascaderLevel(
                                  index,
                                  'description',
                                  e.target.value
                                )
                              }
                              className='col-span-3'
                              placeholder='可选描述'
                            />
                          </div>
                        </div>

                        <Button
                          variant='ghost'
                          size='icon'
                          className='absolute top-2 right-2 h-6 w-6 text-destructive opacity-0 group-hover:opacity-100 transition-opacity'
                          onClick={() => handleDeleteCascaderLevel(index)}
                        >
                          <Trash2 className='h-4 w-4' />
                        </Button>
                      </div>
                    ))
                  ) : (
                    <div className='text-center text-gray-500 p-4 border-2 border-dashed rounded-lg'>
                      暂无级联层级，请添加第一个层级
                    </div>
                  )}

                  <Button
                    variant='outline'
                    className='w-full border-dashed'
                    onClick={handleAddCascaderLevel}
                  >
                    <Plus className='h-4 w-4 mr-2' />
                    添加级联层级
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            取消
          </Button>
          <Button
            onClick={handleSaveParam}
            disabled={
              (paramType === 'plain' && (!plainName || !plainChoices.length)) ||
              (paramType === 'cascader' &&
                (!cascaderDfAlias ||
                  !cascaderLevels.length ||
                  cascaderLevels.some(
                    (level) => !level.dfColumn || !level.name
                  )))
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
