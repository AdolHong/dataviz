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
import { Check, ChevronsUpDown, Plus, Pencil, Trash2 } from 'lucide-react';
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
import { toast } from 'sonner';
import type { Artifact, DataSource, ArtifactParam } from '@/types';
import EditArtifactParamModal from './EditArtifactParamModal';

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
  const [artifactParams, setArtifactParams] = useState<ArtifactParam[]>([]);

  // UI 状态控制
  const [openEngine, setOpenEngine] = useState(false);
  const [openDependencies, setOpenDependencies] = useState(false);
  const [isParamModalOpen, setIsParamModalOpen] = useState(false);
  const [editingParam, setEditingParam] = useState<ArtifactParam | null>(null);

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
      setArtifactParams(artifact.ArtifactParams || []);
    } else {
      // 新增模式：重置所有状态
      setId(generateId());
      setTitle('');
      setDescription('');
      setCode('');
      setDependencies([]);
      setExecutorEngine('default');
      setArtifactParams([]);
    }
  }, [artifact, isOpen]);

  // --- 参数相关操作 ---
  const handleAddParam = (param: ArtifactParam) => {
    setArtifactParams((prev) => [...prev, param]);
    setIsParamModalOpen(false);
  };

  const handleEditParam = (param: ArtifactParam) => {
    setArtifactParams((prev) =>
      prev.map((p) => (p.id === param.id ? param : p))
    );
    setEditingParam(null);
    setIsParamModalOpen(false);
  };

  const handleDeleteParam = (paramId: string) => {
    setArtifactParams((prev) => prev.filter((p) => p.id !== paramId));
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

      const savedArtifact: Artifact = {
        id: artifact?.id || id,
        title,
        description: description || '',
        code: code || '',
        dependencies: dependencies || [],
        executor_engine: executor_engine || 'default',
        ArtifactParams: artifactParams,
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
      <DialogContent className='sm:max-w-[650px]'>
        <DialogHeader>
          <DialogTitle>{artifact ? '编辑图表' : '添加图表'}</DialogTitle>
        </DialogHeader>

        <div className='grid gap-4 py-4'>
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
              <Popover open={openEngine} onOpenChange={setOpenEngine}>
                <PopoverTrigger asChild>
                  <Button
                    variant='outline'
                    role='combobox'
                    aria-expanded={openEngine}
                    className='w-full justify-between'
                  >
                    {executor_engine || '选择执行引擎'}
                    <ChevronsUpDown className='ml-2 h-4 w-4 shrink-0 opacity-50' />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className='w-full p-0'>
                  <Command>
                    <CommandInput placeholder='搜索引擎...' />
                    <CommandList>
                      <CommandEmpty>没有找到匹配的引擎</CommandEmpty>
                      <CommandGroup>
                        {engineChoices.map((engine) => (
                          <CommandItem
                            key={engine}
                            value={engine}
                            onSelect={(currentValue) => {
                              setExecutorEngine(currentValue);
                              setOpenEngine(false);
                            }}
                          >
                            <Check
                              className={cn(
                                'mr-2 h-4 w-4',
                                executor_engine === engine
                                  ? 'opacity-100'
                                  : 'opacity-0'
                              )}
                            />
                            {engine}
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            </div>
          </div>

          <div className='grid grid-cols-4 items-start gap-4'>
            <Label htmlFor='dependencies' className='text-right pt-2'>
              数据源依赖*
            </Label>
            <div className='col-span-3'>
              <Popover
                open={openDependencies}
                onOpenChange={setOpenDependencies}
              >
                <PopoverTrigger asChild>
                  <Button
                    variant='outline'
                    role='combobox'
                    aria-expanded={openDependencies}
                    className='w-full justify-between'
                  >
                    {dependencies.length > 0
                      ? dependencies.join(', ')
                      : '选择数据源依赖'}
                    <ChevronsUpDown className='ml-2 h-4 w-4 shrink-0 opacity-50' />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className='w-full p-0'>
                  <Command>
                    <CommandInput placeholder='搜索数据源...' />
                    <CommandList>
                      <CommandEmpty>没有找到匹配的数据源</CommandEmpty>
                      <CommandGroup>
                        {dataSourceOptions.map((alias) => (
                          <CommandItem
                            key={alias}
                            value={alias}
                            onSelect={() => {
                              setDependencies((prev) =>
                                prev.includes(alias)
                                  ? prev.filter((a) => a !== alias)
                                  : [...prev, alias]
                              );
                              // 多选不关闭弹窗
                            }}
                          >
                            <Check
                              className={cn(
                                'mr-2 h-4 w-4',
                                dependencies.includes(alias)
                                  ? 'opacity-100'
                                  : 'opacity-0'
                              )}
                            />
                            {alias}
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            </div>
          </div>

          <div className='grid grid-cols-4 items-start gap-4'>
            <Label className='text-right pt-2'>参数列表</Label>
            <div className='col-span-3 space-y-2'>
              {artifactParams.length > 0 ? (
                <div className='space-y-2'>
                  {artifactParams.map((param) => (
                    <div
                      key={param.id}
                      className='border-2 rounded-lg p-3 text-sm relative group shadow-sm'
                    >
                      <div className='font-medium'>
                        {param.name} {param.alias ? `(${param.alias})` : ''}
                      </div>
                      <div className='text-xs text-gray-500'>
                        {param.description || '无描述'} · {param.valueType} ·{' '}
                        {param.paramType.type}
                      </div>

                      <div className='absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-80 transition-opacity'>
                        <Button
                          variant='ghost'
                          size='icon'
                          className='h-6 w-6'
                          onClick={() => {
                            setEditingParam(param);
                            setIsParamModalOpen(true);
                          }}
                        >
                          <Pencil className='h-4 w-4' />
                        </Button>
                        <Button
                          variant='ghost'
                          size='icon'
                          className='h-6 w-6 text-destructive'
                          onClick={() => handleDeleteParam(param.id)}
                        >
                          <Trash2 className='h-4 w-4' />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className='text-center text-gray-500 p-4 border-2 border-dashed rounded-lg'>
                  暂无参数
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
              代码*
            </Label>
            <Textarea
              id='code'
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className='col-span-3 min-h-[200px]'
              placeholder='输入图表代码'
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            取消
          </Button>
          <Button
            onClick={handleSaveClick}
            disabled={!title || !code || dependencies.length === 0}
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
        onSave={editingParam ? handleEditParam : handleAddParam}
        param={editingParam}
        dataSources={dataSources}
      />
    </Dialog>
  );
};

export default EditArtifactModal;
