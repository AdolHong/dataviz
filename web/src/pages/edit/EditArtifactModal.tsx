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
import { Plus, Pencil, Trash2 } from 'lucide-react';

import { toast } from 'sonner';
import type {
  Artifact,
  DataSource,
  SinglePlainParam,
  MultiplePlainParam,
  CascaderParam,
} from '@/types';
import EditArtifactParamModal from './EditArtifactParamModal';
import { Combobox } from '@/components/combobox';

// 引入 AceEditor 相关依赖
import AceEditor from 'react-ace';
import 'ace-builds/src-noconflict/theme-xcode';
import 'ace-builds/src-noconflict/mode-python';

interface EditArtifactModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (artifact: Artifact) => void;
  artifact: Artifact | null; // 接收要编辑的图表，null 表示新增
  dataSources: DataSource[]; // 可选的数据源列表
  engineChoices: string[]; // 可用的引擎选项
}

// 辅助函数生成唯一 ID
const generateId = () =>
  `artifact_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;

const EditArtifactModal = ({
  isOpen,
  onClose,
  onSave,
  artifact,
  dataSources,
  engineChoices = ['default', 'pandas', 'numpy'],
}: EditArtifactModalProps) => {
  // --- 表单状态 ---
  const [id, setId] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [code, setCode] = useState('');
  const [dependencies, setDependencies] = useState<string[]>([]);
  const [executor_engine, setExecutorEngine] = useState('default');
  const [plainParams, setPlainParams] = useState<
    (SinglePlainParam | MultiplePlainParam)[]
  >([]);
  const [cascaderParams, setCascaderParams] = useState<CascaderParam[]>([]);

  const [plainParamNames, setPlainParamNames] = useState<string[]>([]);

  // UI 状态控制
  const [isParamModalOpen, setIsParamModalOpen] = useState(false);
  const [editingParam, setEditingParam] = useState<{
    param: SinglePlainParam | MultiplePlainParam | CascaderParam;
    type: 'plain' | 'cascader';
    id: string;
  } | null>(null);

  // 数据源别名列表（供依赖选择用）
  const dataSourceOptions = dataSources.map((ds) => ds.alias);

  // --- 效果钩子 ---
  useEffect(() => {
    if (artifact) {
      // 编辑模式：填充现有数据
      setId(artifact.id);
      setTitle(artifact.title);
      setDescription(artifact.description || '');
      setCode(artifact.code);
      setDependencies(artifact.dependencies);
      setExecutorEngine(artifact.executor_engine);
      setPlainParams(artifact.plainParams || []);
      setCascaderParams(artifact.cascaderParams || []);
      setPlainParamNames(artifact.plainParams?.map((p) => p.name) || []);
    } else {
      // 新增模式：重置所有状态
      setId(generateId());
      setTitle('');
      setDescription('');
      setCode('');
      setDependencies([]);
      setExecutorEngine('default');
      setPlainParams([]);
      setCascaderParams([]);
      setPlainParamNames([]);
    }
  }, [artifact, isOpen]);

  // --- 参数相关操作 ---
  const handleAddParam = (
    param: SinglePlainParam | MultiplePlainParam | CascaderParam
  ) => {
    if ('type' in param) {
      // 处理 Plain 参数
      setPlainParams((prev) => [
        ...prev,
        param as SinglePlainParam | MultiplePlainParam,
      ]);
    } else {
      // 处理 Cascader 参数
      setCascaderParams((prev) => [...prev, param as CascaderParam]);
    }
    setIsParamModalOpen(false);
  };

  const handleEditParam = (
    param: SinglePlainParam | MultiplePlainParam | CascaderParam,
    paramType: 'plain' | 'cascader',
    originalId: string
  ) => {
    if (paramType === 'plain') {
      setPlainParams((prev) =>
        prev.map((p) =>
          p.id === originalId
            ? (param as SinglePlainParam | MultiplePlainParam)
            : p
        )
      );
    } else {
      setCascaderParams((prev) =>
        prev.map((p, index) =>
          index === parseInt(originalId) ? (param as CascaderParam) : p
        )
      );
    }
    setEditingParam(null);
    setIsParamModalOpen(false);
  };

  const handleDeleteParam = (
    paramId: string,
    paramType: 'plain' | 'cascader'
  ) => {
    if (paramType === 'plain') {
      setPlainParams((prev) => prev.filter((p) => p.id !== paramId));
    } else {
      setCascaderParams((prev) =>
        prev.filter((_, index) => index.toString() !== paramId)
      );
    }
  };

  // --- 事件处理 ---
  const handleSaveClick = () => {
    try {
      // 基本验证
      if (!title.trim()) {
        toast.error('图表标题不能为空');
        return;
      }

      if (!code.trim()) {
        toast.error('图表代码不能为空');
        return;
      }

      if (dependencies.length === 0) {
        toast.error('请至少选择一个数据源依赖');
        return;
      }

      console.info('artifact', artifact);
      const savedArtifact: Artifact = {
        id: artifact?.id || id,
        title,
        description: description || '',
        code: code || '',
        dependencies: dependencies || [],
        executor_engine: executor_engine || 'default',
        plainParams: plainParams.length > 0 ? plainParams : undefined,
        cascaderParams: cascaderParams.length > 0 ? cascaderParams : undefined,
      };
      onSave(savedArtifact);
    } catch (error) {
      console.error('Error saving artifact:', error);
      toast.error('保存图表时发生错误');
    }
  };

  // --- JSX ---
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className='max-w-[650px] '>
        <DialogHeader>
          <DialogTitle>{artifact ? '编辑图表' : '添加图表'}</DialogTitle>
        </DialogHeader>

        <div className='grid gap-4 py-4 pr-2 max-h-[70vh] overflow-y-auto'>
          <div className='grid grid-cols-4 items-center gap-4'>
            <Label htmlFor='title' className='text-right'>
              标题*
            </Label>
            <Input
              id='title'
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className='col-span-3'
              required
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
              placeholder='（可选）图表描述'
            />
          </div>

          <div className='grid grid-cols-4 items-center gap-4'>
            <Label htmlFor='executor-engine' className='text-right'>
              执行引擎*
            </Label>
            <div className='col-span-3'>
              <Combobox
                options={engineChoices}
                value={executor_engine || 'default'}
                onValueChange={(value: string | string[]) => {
                  if (Array.isArray(value)) {
                    setExecutorEngine(value[0]);
                  } else {
                    console.log('engine value:', value);
                    setExecutorEngine(value || 'default');
                  }
                }}
                mode='single' // 单选
                placeholder='选择执行引擎'
              />
            </div>
          </div>

          <div className='grid grid-cols-4 items-start gap-4'>
            <Label className='text-right pt-2'>数据源依赖*</Label>
            <div className='col-span-3'>
              <Combobox
                options={dataSourceOptions}
                value={dependencies}
                onValueChange={(value: string | string[]) => {
                  if (Array.isArray(value)) {
                    setDependencies(value);
                  } else {
                    setDependencies((prev) =>
                      prev.includes(value)
                        ? prev.filter((a) => a !== value)
                        : [...prev, value]
                    );
                  }
                }}
                mode='multiple' // 允许多选
                placeholder='选择数据源依赖'
              />
            </div>
          </div>

          <div className='grid grid-cols-4 items-start gap-4'>
            <Label className='text-right pt-2'>参数列表</Label>
            <div className='col-span-3 pt-1 space-y-2'>
              {/* Plain 参数列表 */}
              {plainParams.length > 0 && (
                <div className='space-y-2'>
                  <h4 className='text-sm font-medium'>普通参数</h4>
                  {plainParams.map((param) => (
                    <div
                      key={param.id}
                      className='border-2 rounded-lg p-3 text-sm relative group shadow-sm'
                    >
                      <div className='font-medium'>
                        {param.name} {param.alias ? `(${param.alias})` : ''}
                      </div>
                      <div className='text-xs text-gray-500'>
                        {param.description || '无描述'} · {param.valueType} ·{' '}
                        {param.type}
                      </div>

                      <div className='absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-80 transition-opacity'>
                        <Button
                          variant='ghost'
                          size='icon'
                          className='h-6 w-6'
                          onClick={() => {
                            setEditingParam({
                              param,
                              type: 'plain',
                              id: param.id,
                            });
                            setIsParamModalOpen(true);
                          }}
                        >
                          <Pencil className='h-4 w-4' />
                        </Button>
                        <Button
                          variant='ghost'
                          size='icon'
                          className='h-6 w-6 text-destructive'
                          onClick={() => handleDeleteParam(param.id, 'plain')}
                        >
                          <Trash2 className='h-4 w-4' />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Cascader 参数列表 */}
              {cascaderParams.length > 0 && (
                <div className='space-y-2'>
                  <h4 className='text-sm font-medium'>级联参数</h4>
                  {cascaderParams.map((param, index) => (
                    <div
                      key={index}
                      className='border-2 rounded-lg p-3 text-sm relative group shadow-sm'
                    >
                      <div className='font-medium'>数据源: {param.dfAlias}</div>
                      <ul className='text-xs mt-1'>
                        {param.levels.map((level, levelIndex) => (
                          <li key={levelIndex}>
                            level {levelIndex + 1}: {level.dfColumn}{' '}
                            {level.name && `(别名: ${level.name})`}
                          </li>
                        ))}
                      </ul>

                      <div className='absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-80 transition-opacity'>
                        <Button
                          variant='ghost'
                          size='icon'
                          className='h-6 w-6'
                          onClick={() => {
                            setEditingParam({
                              param,
                              type: 'cascader',
                              id: index.toString(),
                            });
                            setIsParamModalOpen(true);
                          }}
                        >
                          <Pencil className='h-4 w-4' />
                        </Button>
                        <Button
                          variant='ghost'
                          size='icon'
                          className='h-6 w-6 text-destructive'
                          onClick={() =>
                            handleDeleteParam(index.toString(), 'cascader')
                          }
                        >
                          <Trash2 className='h-4 w-4' />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {plainParams.length === 0 && cascaderParams.length === 0 && (
                <div className='text-center text-gray-500 p-4 border-2 border-dashed rounded-lg'>
                  暂无参数(可选)
                </div>
              )}

              <Button
                variant='outline'
                className='w-full border-dashed mt-2'
                onClick={() => {
                  setEditingParam(null);
                  setIsParamModalOpen(true);
                }}
              >
                <Plus className='h-4 w-4 mr-2' />
                新增参数
              </Button>
            </div>
          </div>

          <div className='grid grid-cols-4 items-start gap-4'>
            <Label htmlFor='code' className='text-right pt-2'>
              Python代码*
            </Label>
            <div className='col-span-3'>
              <AceEditor
                mode='python'
                theme='xcode'
                name='artifactCodeEditor'
                height='200px'
                width='100%'
                onChange={(value) => setCode(value)}
                value={code}
                setOptions={{
                  enableBasicAutocompletion: true,
                  enableLiveAutocompletion: true,
                  enableSnippets: true,
                  showLineNumbers: true,
                  tabSize: 2,
                }}
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            取消
          </Button>
          <Button
            onClick={handleSaveClick}
            disabled={
              !title || !code || dependencies.length === 0 || !executor_engine
            }
          >
            保存
          </Button>
        </DialogFooter>
      </DialogContent>

      {/* 参数编辑模态框 */}
      <EditArtifactParamModal
        isOpen={isParamModalOpen}
        onClose={() => {
          setIsParamModalOpen(false);
          setEditingParam(null);
        }}
        onSave={
          editingParam
            ? (param: SinglePlainParam | MultiplePlainParam | CascaderParam) =>
                handleEditParam(param, editingParam.type, editingParam.id)
            : handleAddParam
        }
        paramData={editingParam}
        plainParamNames={plainParamNames}
        setPlainParamNames={setPlainParamNames}
        dependencies={dependencies}
      />
    </Dialog>
  );
};

export default EditArtifactModal;
