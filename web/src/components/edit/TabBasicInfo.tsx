import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { EditIcon } from 'lucide-react';

interface TabBasicInfoProps {
  title: string;
  description: string;
  onUpdate: (title: string, description: string) => void;
  titleEditable?: boolean;
}

const TabBasicInfo = ({
  title,
  description,
  onUpdate,
  titleEditable,
}: TabBasicInfoProps) => {
  const [isEditing, setIsEditing] = useState(false);
  const [newTitle, setNewTitle] = useState(title || 'default_title');
  const [newDescription, setNewDescription] = useState(description || '');

  const handleSave = () => {
    if (!newTitle.trim()) {
      toast.error('报表标题不能为空');
      return;
    }
    // 检查标题是否包含特殊字符
    const invalidChars = /[<>:"/\\|?*\x00-\x1F]/; // Linux 文件名不允许的字符
    if (invalidChars.test(newTitle)) {
      toast.error('报表标题包含不允许的字符');
      return;
    }

    onUpdate(newTitle, newDescription);
    setIsEditing(false);
    toast.success('基本信息已更新');
  };

  const handleCancel = () => {
    setIsEditing(false);
  };

  return (
    <div className='p-6 space-y-6'>
      <Card className='shadow-sm'>
        <CardContent className='pt-6 pb-6'>
          {isEditing ? (
            <div className='space-y-4'>
              <div className='grid grid-cols-4 items-center gap-4'>
                {titleEditable && (
                  <>
                    <Label htmlFor='title' className='text-right font-medium'>
                      报表标题<span className='text-red-500'>*</span>
                    </Label>

                    <Input
                      id='title'
                      value={newTitle}
                      onChange={(e) => setNewTitle(e.target.value)}
                      className='col-span-3'
                      placeholder='请输入报表标题'
                      required
                    />
                  </>
                )}
              </div>

              <div className='grid grid-cols-4 items-start gap-4'>
                <Label
                  htmlFor='description'
                  className='text-right font-medium pt-2'
                >
                  报表描述
                </Label>
                <Textarea
                  id='description'
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  className='col-span-3 min-h-[100px] max-h-[200px] overflow-y-auto'
                  placeholder='请输入报表描述（可选）'
                />
              </div>

              <div className='flex justify-end space-x-2 pt-4'>
                <Button variant='outline' onClick={handleCancel}>
                  取消
                </Button>
                <Button onClick={handleSave} disabled={!newTitle.trim()}>
                  保存
                </Button>
              </div>
            </div>
          ) : (
            <div className='space-y-4'>
              {titleEditable && (
                <div className='grid grid-cols-4 gap-4'>
                  <div className='text-right font-medium'>报表标题:</div>
                  <div className='col-span-3'>{title}</div>
                </div>
              )}

              <div className='grid grid-cols-4 gap-4'>
                <div className='text-right font-medium'>报表描述:</div>
                <div className='col-span-3'>{description || '无描述'}</div>
              </div>

              <div className='flex justify-end pt-4'>
                <Button
                  variant='outline'
                  onClick={() => setIsEditing(true)}
                  className='flex items-center gap-1'
                >
                  <EditIcon className='h-4 w-4' />
                  编辑信息
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default TabBasicInfo;
