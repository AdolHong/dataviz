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
import { toast } from 'sonner';
import type { Artifact, DataSource } from '@/types';

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

  // UI 状态控制
  const [openEngine, setOpenEngine] = useState(false);
  const [openDependencies, setOpenDependencies] = useState(false);

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
    } else {
      // 新增模式：重置所有状态
      setId(generateId());
      setTitle('');
      setDescription('');
      setCode('');
      setDependencies([]);
      setExecutorEngine('default');
    }
  }, [artifact, isOpen]);

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
        ArtifactParams: artifact?.ArtifactParams || [],
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
    </Dialog>
  );
};

export default EditArtifactModal;
