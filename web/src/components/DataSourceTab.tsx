import { Button } from '@/components/ui/button';
import { Trash2, Pencil, Plus } from 'lucide-react';
import { type DataSource } from '@/types/models/dataSource';
import { TabsContent } from '@radix-ui/react-tabs';

const DataSourceTab = ({
  dataSources,
  setDataSources,
  handleDeleteDataSource,
  setIsDataSourceModalOpen,
  confirmDelete,
}: {
  dataSources: DataSource[];
  setDataSources: (dataSources: DataSource[]) => void;
  handleDeleteDataSource: (id: string) => void;
  setIsDataSourceModalOpen: (open: boolean) => void;
  confirmDelete: (deleteFunction: () => void, message: string) => void;
}) => {
  return (
    <div>
      <TabsContent value='data' className='p-4'>
        <div className='space-y-4'>
          <div className='space-y-3'>
            {dataSources.map((dataSource, idx) => (
              <div
                key={dataSource.id}
                className='border rounded-lg p-4 bg-white shadow-sm'
              >
                <div className='flex justify-between items-center'>
                  <div>
                    <div className='flex items-center gap-2'>
                      <h4 className='font-medium'>{dataSource.name}</h4>
                      <p className='text-sm text-gray-500'>
                        {idx === 0 ? '(df, df1)' : `(df${idx + 1})`}
                      </p>
                    </div>
                    <p className='text-sm text-gray-500'>
                      type: {dataSource.executor.type}
                    </p>
                  </div>
                  <div className='flex gap-2'>
                    <Button variant='ghost' size='icon' className='h-8 w-8'>
                      <Pencil className='h-4 w-4' />
                    </Button>
                    <Button
                      variant='ghost'
                      size='icon'
                      className='h-8 w-8 text-destructive'
                      onClick={() =>
                        confirmDelete(
                          () => handleDeleteDataSource(dataSource.id),
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
              onClick={() => setIsDataSourceModalOpen(true)}
            >
              <Plus className='h-4 w-4 mr-2' />
              添加数据源
            </Button>
          </div>
        </div>
      </TabsContent>
    </div>
  );
};

export default DataSourceTab;
