import { Button } from '@/components/ui/button';
import { Trash2, Pencil, Plus } from 'lucide-react';
import { type DataSource } from '@/types/models/dataSource';
import { TabsContent } from '@radix-ui/react-tabs';
import { useState } from 'react';
import { EditDataSourceModal } from './EditDataSourceModal';
import { type AliasRelianceMap } from '@/types/models/aliasRelianceMap';
import { type EngineChoices } from '@/types/models/engineChoices';

interface TabDataSourceProps {
  dataSources: DataSource[];
  setDataSources: (dataSources: DataSource[]) => void;
  engineChoices: EngineChoices;
  aliasRelianceMap: AliasRelianceMap;
  handleAddDataSource: (dataSource: DataSource) => void;
  handleEditDataSource: (
    oldDataSource: DataSource,
    newDataSource: DataSource
  ) => void;
  handleDeleteDataSource: (dataSource: DataSource) => void;
  confirmDelete: (deleteFunction: () => void, message: string) => void;
}

const TabDataSource = ({
  dataSources,
  engineChoices,
  aliasRelianceMap,
  handleAddDataSource,
  handleEditDataSource,
  handleDeleteDataSource,
  confirmDelete,
}: TabDataSourceProps) => {
  const [isEditDataSourceModalOpen, setIsEditDataSourceModalOpen] =
    useState(false);
  const [editingDataSource, setEditingDataSource] = useState<DataSource | null>(
    null
  );
  return (
    <div>
      <TabsContent value='data' className='p-4'>
        <div className='space-y-4'>
          <div className='space-y-3'>
            {dataSources.map((dataSource) => (
              <div
                key={dataSource.id}
                className='border rounded-lg p-4 bg-white shadow-sm'
              >
                <div className='flex justify-between items-center'>
                  <div>
                    <h4 className='font-medium'>{dataSource.name}</h4>
                    <div className='flex items-center gap-4'>
                      <p className='text-sm text-gray-500 w-25'>
                        type: {dataSource.executor.type}
                      </p>
                      <p className='text-sm text-gray-500'>
                        alias: {dataSource.alias}
                      </p>
                    </div>
                  </div>
                  <div className='flex gap-2'>
                    <Button
                      variant='ghost'
                      size='icon'
                      className='h-8 w-8 opacity-80'
                      onClick={() => {
                        console.log('clickdataSource', dataSource);
                        setEditingDataSource(dataSource);
                        setIsEditDataSourceModalOpen(true);
                      }}
                    >
                      <Pencil className='h-4 w-4' />
                    </Button>
                    <Button
                      variant='ghost'
                      size='icon'
                      className='h-8 w-8 text-destructive opacity-80'
                      onClick={() =>
                        confirmDelete(
                          () => handleDeleteDataSource(dataSource),
                          `您确定要删除数据源 ${dataSource.name} 吗？`
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
              onClick={() => setIsEditDataSourceModalOpen(true)}
            >
              <Plus className='h-4 w-4 mr-2' />
              添加数据源
            </Button>
          </div>
        </div>
      </TabsContent>

      <EditDataSourceModal
        open={isEditDataSourceModalOpen}
        onClose={() => {
          setIsEditDataSourceModalOpen(false);
          setEditingDataSource(null);
        }}
        onSave={(updatedDataSource: DataSource) => {
          if (editingDataSource) {
            // 若是编辑, 则alias可能变化； 需要传递oldDataSource
            handleEditDataSource(editingDataSource, updatedDataSource);
          } else {
            handleAddDataSource(updatedDataSource);
          }
          setIsEditDataSourceModalOpen(false);
          setEditingDataSource(null);
        }}
        initialDataSource={editingDataSource}
        engineChoices={engineChoices}
        existingAliases={dataSources
          .filter((ds) =>
            editingDataSource ? ds.id !== editingDataSource.id : true
          )
          .map((ds) => ds.alias)}
        aliasRelianceMap={aliasRelianceMap}
      />
    </div>
  );
};

export default TabDataSource;
