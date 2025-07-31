import { Button } from '@/components/ui/button';
import { Trash2, Pencil, Plus, GripVertical } from 'lucide-react';
import { type Parameter } from '@/types/models/parameter';
import { TabsContent } from '@radix-ui/react-tabs';
import { useState } from 'react';
import EditFilterModal from './EditFilterModal';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';

import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import {
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

interface TabFilterProps {
  parameters: Parameter[];
  handleAddParameter: (parameter: Parameter) => boolean;
  handleEditParameter: (parameter: Parameter) => boolean;
  handleDeleteParameter: (parameter: Parameter) => void;
  handleReorderParameters: (newOrder: Parameter[]) => void;
  confirmDelete: (deleteFunction: () => void, message: string) => void;
}

// 可拖拽的筛选条件项组件
const SortableFilterItem = ({ 
  parameter, 
  onEdit, 
  onDelete 
}: { 
  parameter: Parameter; 
  onEdit: (parameter: Parameter) => void;
  onDelete: (parameter: Parameter) => void;
}) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: parameter.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`border rounded-lg p-4 bg-white shadow-sm ${
        isDragging ? 'shadow-lg' : ''
      }`}
    >
      <div className='flex justify-between items-center'>
        <div className='flex items-center gap-3'>
          <div
            {...attributes}
            {...listeners}
            className='cursor-grab active:cursor-grabbing p-1 hover:bg-gray-100 rounded'
          >
            <GripVertical className='h-4 w-4 text-gray-400' />
          </div>
          <div>
            <h4 className='font-medium'>
              {parameter.name}{' '}
              {parameter.alias && `(alias: ${parameter.alias})`}
            </h4>
            <p className='text-sm text-gray-500'>
              type: {parameter.config.type}
            </p>
          </div>
        </div>
        <div className='flex gap-2'>
          <Button
            variant='ghost'
            size='icon'
            className='h-8 w-8 opacity-80'
            onClick={() => onEdit(parameter)}
          >
            <Pencil className='h-4 w-4' />
          </Button>
          <Button
            variant='ghost'
            size='icon'
            className='h-8 w-8 text-destructive opacity-80'
            onClick={() => onDelete(parameter)}
          >
            <Trash2 className='h-4 w-4' />
          </Button>
        </div>
      </div>
    </div>
  );
};

const TabFilter = ({
  parameters,
  handleAddParameter,
  handleEditParameter,
  handleDeleteParameter,
  handleReorderParameters,
  confirmDelete,
}: TabFilterProps) => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingParameter, setEditingParameter] = useState<Parameter | null>(
    null
  );

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
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
    let successFlag: boolean = false;
    if (editingParameter) {
      successFlag = handleEditParameter(parameter);
    } else {
      successFlag = handleAddParameter(parameter);
    }
    if (successFlag) {
      closeModal();
    }
  };

  const handleDragEnd = (event: any) => {
    const { active, over } = event;

    if (active.id !== over?.id) {
      const oldIndex = parameters.findIndex(param => param.id === active.id);
      const newIndex = parameters.findIndex(param => param.id === over?.id);
      
      const newOrder = arrayMove(parameters, oldIndex, newIndex);
      handleReorderParameters(newOrder);
    }
  };

  const handleEdit = (parameter: Parameter) => {
    openModal(parameter);
  };

  const handleDelete = (parameter: Parameter) => {
    confirmDelete(
      () => handleDeleteParameter(parameter),
      `您确定要删除筛选条件"${parameter.name}"吗？`
    );
  };

  return (
    <>
      <TabsContent value='filters' className='p-4'>
        <div className='space-y-4'>
          <div className='space-y-3'>
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={parameters.map(param => param.id)}
                strategy={verticalListSortingStrategy}
              >
                {parameters.map((parameter) => (
                  <SortableFilterItem
                    key={parameter.id}
                    parameter={parameter}
                    onEdit={handleEdit}
                    onDelete={handleDelete}
                  />
                ))}
              </SortableContext>
            </DndContext>
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
