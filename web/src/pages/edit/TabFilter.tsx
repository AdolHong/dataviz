import { Button } from '@/components/ui/button';
import { Trash2, Pencil, Plus } from 'lucide-react';
import { type Parameter } from '@/types/models/parameter';
import { TabsContent } from '@radix-ui/react-tabs';
import { useState } from 'react';
import EditFilterModal from './EditFilterModal';

interface TabFilterProps {
  parameters: Parameter[];
  setParameters: (parameters: Parameter[]) => void;
  handleUpsertParameter: (parameter: Parameter | null) => void;
  handleDeleteParameter: (parameter: Parameter) => void;
  confirmDelete: (deleteFunction: () => void, message: string) => void;
}

const TabFilter = ({
  parameters,
  handleUpsertParameter,
  handleDeleteParameter,
  confirmDelete,
}: TabFilterProps) => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingParameter, setEditingParameter] = useState<Parameter | null>(
    null
  );

  const openModal = (parameter: Parameter | null) => {
    setEditingParameter(parameter);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingParameter(null);
  };

  const handleSave = (parameter: Parameter) => {
    handleUpsertParameter(parameter);
    closeModal();
  };

  return (
    <>
      <TabsContent value='filters' className='p-4'>
        <div className='space-y-4'>
          <div className='space-y-3'>
            {parameters.map((parameter) => (
              <div
                key={parameter.id}
                className='border rounded-lg p-4 bg-white shadow-sm'
              >
                <div className='flex justify-between items-center'>
                  <div>
                    <h4 className='font-medium'>{parameter.name}</h4>
                    {parameter.alias && (
                      <p className='text-sm text-gray-600'>
                        别名: {parameter.alias}
                      </p>
                    )}
                    <p className='text-sm text-gray-500'>
                      类型: {parameter.paramConfig.type}
                    </p>
                    {parameter.description && (
                      <p className='text-xs text-gray-400 mt-1'>
                        {parameter.description}
                      </p>
                    )}
                  </div>
                  <div className='flex gap-2'>
                    <Button
                      variant='ghost'
                      size='icon'
                      className='h-8 w-8 opacity-80'
                      onClick={() => openModal(parameter)}
                    >
                      <Pencil className='h-4 w-4' />
                    </Button>
                    <Button
                      variant='ghost'
                      size='icon'
                      className='h-8 w-8 text-destructive opacity-80'
                      onClick={() =>
                        confirmDelete(
                          () => handleDeleteParameter(parameter),
                          `您确定要删除筛选条件"${parameter.name}"吗？`
                        )
                      }
                    >
                      <Trash2 className='h-4 w-4' />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className='mt-6'>
            <Button
              variant='outline'
              className='w-full border-dashed'
              onClick={() => openModal(null)}
            >
              <Plus className='h-4 w-4 mr-2' />
              添加筛选条件
            </Button>
          </div>
        </div>
      </TabsContent>
      <EditFilterModal
        isOpen={isModalOpen}
        onClose={closeModal}
        onSave={handleSave}
        parameter={editingParameter}
      />
    </>
  );
};

export default TabFilter;
