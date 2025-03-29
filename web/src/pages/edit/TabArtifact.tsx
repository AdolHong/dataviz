import { Button } from '@/components/ui/button';
import { Trash2, Pencil, Plus } from 'lucide-react';
import { TabsContent } from '@/components/ui/tabs';
import { type Layout } from '@/types/models/layout';
import { useState } from 'react';
import { EditLayoutModal } from './EditLayoutModal';
import EditArtifactModal from './EditArtifactModal';
import type { Artifact, DataSource } from '@/types';
import { toast } from 'sonner';

interface TabArtifactProps {
  layout: Layout;
  setLayout: (layout: Layout) => void;
  handleAddArtifact: () => void;
  handleModifyArtifact: (artifact: Artifact) => void;
  handleDeleteArtifact: (id: string) => void;
  confirmDelete: (deleteFunction: () => void, message: string) => void;
  artifacts: Artifact[];
  dataSources: DataSource[];
  engineChoices: string[];
}

const TabArtifact = ({
  layout,
  setLayout,
  handleAddArtifact,
  handleModifyArtifact,
  handleDeleteArtifact,
  confirmDelete,
  artifacts,
  dataSources,
  engineChoices,
}: TabArtifactProps) => {
  console.info('dataSources222', dataSources);

  const [isLayoutModalOpen, setIsLayoutModalOpen] = useState(false);
  const [isArtifactModalOpen, setIsArtifactModalOpen] = useState(false);
  const [editingArtifact, setEditingArtifact] = useState<Artifact | null>(null);

  // 处理图表保存
  const handleSaveArtifact = (artifact: Artifact) => {
    if (editingArtifact) {
      handleModifyArtifact(artifact);
    } else {
      handleAddArtifact(artifact);
    }
    setIsArtifactModalOpen(false);
  };

  return (
    <div>
      <TabsContent value='artifacts' className='p-4'>
        <div className='space-y-4'>
          <div className='border rounded-lg p-4'>
            {layout ? (
              <div
                className='grid gap-4 relative'
                style={{
                  gridTemplateColumns: `repeat(${layout.columns}, 1fr)`,
                  gridTemplateRows: `repeat(${layout.rows}, 100px)`,
                  minHeight: '100px',
                }}
              >
                {layout.items.map((item) => (
                  <div
                    key={item.id}
                    className='border-2 rounded-lg p-4 text-center flex items-center justify-center relative group shadow-sm'
                    style={{
                      gridColumn: `${item.x + 1} / span ${item.width}`,
                      gridRow: `${item.y + 1} / span ${item.height}`,
                    }}
                  >
                    {item.title}
                    <div className='absolute bottom-0 flex gap-1 opacity-0 group-hover:opacity-80 transition-opacity'>
                      <Button
                        variant='ghost'
                        size='icon'
                        className='h-6 w-6'
                        onClick={() => {
                          const artifact = artifacts.find(
                            (a) => a.id === item.id
                          );
                          if (artifact) {
                            setEditingArtifact(artifact);
                            setIsArtifactModalOpen(true);
                          } else {
                            toast.error('图表不存在');
                          }
                        }}
                      >
                        <Pencil className='h-4 w-4' />
                      </Button>
                      <Button
                        variant='ghost'
                        size='icon'
                        className='h-6 w-6 text-destructive'
                        onClick={() =>
                          confirmDelete(
                            () => handleDeleteArtifact(item.id),
                            `您确定要删除 "${item.title}" 吗？`
                          )
                        }
                      >
                        <Trash2 className='h-4 w-4' />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className='text-center p-4'>正在加载布局...</div>
            )}
          </div>

          <div className='mt-6'>
            <Button
              variant='outline'
              className='w-full border-dashed'
              onClick={() => {
                setEditingArtifact(null);
                setIsArtifactModalOpen(true);
              }}
            >
              <Plus className='h-4 w-4 mr-2' />
              添加图表
            </Button>
            <Button
              variant='outline'
              className='w-full border-dashed mt-2'
              onClick={() => setIsLayoutModalOpen(true)}
            >
              <Plus className='h-4 w-4 mr-2' />
              修改布局
            </Button>
          </div>
        </div>
      </TabsContent>

      {/* 图表编辑对话框 */}
      <EditArtifactModal
        isOpen={isArtifactModalOpen}
        onClose={() => setIsArtifactModalOpen(false)}
        onSave={handleSaveArtifact}
        artifact={editingArtifact}
        dataSources={dataSources}
        engineChoices={engineChoices}
      />

      {/* 布局编辑对话框 */}
      <EditLayoutModal
        open={isLayoutModalOpen}
        onClose={() => setIsLayoutModalOpen(false)}
        onSave={(newLayout: Layout) => {
          setLayout(newLayout);
          setIsLayoutModalOpen(false);
        }}
        initialLayout={layout}
      />
    </div>
  );
};

export default TabArtifact;
