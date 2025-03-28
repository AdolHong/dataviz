import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { type DataSource } from '@/types/models/dataSource';

interface EditDataSourceModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (dataSource: DataSource) => void;
  initialDataSource?: DataSource | null;
}

export const EditDataSourceModal = ({
  open,
  onClose,
  onSave,
  initialDataSource = null,
}: EditDataSourceModalProps) => {
  const [dataSource, setDataSource] = useState<Partial<DataSource>>({
    name: '',
    description: '',
    executor: {
      type: 'pandas',
      engine: 'python',
    },
    code: '',
    updateMode: {
      type: 'manual',
      interval: undefined,
    },
  });

  // 当打开模态框或初始数据源变化时重置表单数据
  useEffect(() => {
    if (initialDataSource) {
      setDataSource({
        id: initialDataSource.id,
        name: initialDataSource.name || '',
        description: initialDataSource.description || '',
        executor: {
          type: initialDataSource.executor?.type || 'pandas',
          engine: initialDataSource.executor?.engine || 'python',
        },
        code: initialDataSource.code || '',
        updateMode: {
          type: initialDataSource.updateMode?.type || 'manual',
          interval: initialDataSource.updateMode?.interval,
        },
      });
    } else {
      // 重置为初始状态
      setDataSource({
        name: '',
        description: '',
        executor: {
          type: 'pandas',
          engine: 'python',
        },
        code: '',
        updateMode: {
          type: 'manual',
          interval: undefined,
        },
      });
    }
  }, [initialDataSource, open]);

  const handleSave = () => {
    // 简单的验证
    if (!dataSource.name) {
      alert('请输入数据源名称');
      return;
    }

    const finalDataSource: DataSource = {
      id: dataSource.id || Date.now().toString(), // 如果是新建，生成临时ID
      name: dataSource.name || '',
      description: dataSource.description,
      executor: {
        type: dataSource.executor?.type || 'pandas',
        engine: dataSource.executor?.engine || 'python',
      },
      code: dataSource.code || '',
      updateMode: dataSource.updateMode as {
        type: 'auto' | 'manual';
        interval?: number;
      },
    };

    onSave(finalDataSource);
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {initialDataSource ? '编辑数据源' : '新建数据源'}
          </DialogTitle>
        </DialogHeader>

        <div className='space-y-4'>
          <div>
            <label className='block mb-2'>数据源名称</label>
            <Input
              value={dataSource.name || ''}
              onChange={(e) =>
                setDataSource((prev) => ({ ...prev, name: e.target.value }))
              }
              placeholder='输入数据源名称'
            />
          </div>

          <div>
            <label className='block mb-2'>描述（可选）</label>
            <Textarea
              value={dataSource.description || ''}
              onChange={(e) =>
                setDataSource((prev) => ({
                  ...prev,
                  description: e.target.value,
                }))
              }
              placeholder='输入数据源描述'
            />
          </div>

          <div>
            <label className='block mb-2'>执行类型</label>
            <Select
              value={dataSource.executor?.type || 'pandas'}
              onValueChange={(value) =>
                setDataSource((prev) => ({
                  ...prev,
                  executor: {
                    ...(prev.executor || {}),
                    type: value,
                  },
                }))
              }
            >
              <SelectTrigger>
                <SelectValue placeholder='选择执行类型' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='pandas'>Pandas</SelectItem>
                <SelectItem value='sql'>SQL</SelectItem>
                <SelectItem value='python'>Python</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <label className='block mb-2'>代码</label>
            <Textarea
              value={dataSource.code || ''}
              onChange={(e) =>
                setDataSource((prev) => ({ ...prev, code: e.target.value }))
              }
              placeholder='输入数据处理代码'
              rows={5}
            />
          </div>

          <div>
            <label className='block mb-2'>更新模式</label>
            <Select
              value={dataSource.updateMode?.type || 'manual'}
              onValueChange={(value) =>
                setDataSource((prev) => ({
                  ...prev,
                  updateMode: {
                    ...(prev.updateMode || {}),
                    type: value as 'auto' | 'manual',
                  },
                }))
              }
            >
              <SelectTrigger>
                <SelectValue placeholder='选择更新模式' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='manual'>手动</SelectItem>
                <SelectItem value='auto'>自动</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            取消
          </Button>
          <Button onClick={handleSave}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
