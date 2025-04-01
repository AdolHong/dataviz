import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip';
import { ParameterQueryArea } from './ParameterQueryArea';
import { LayoutGrid } from './LayoutGrid';
import type { DataSource, Layout, Parameter } from '@/types';

interface DashboardContentProps {
  title: string;
  description: string;
  parameters: Parameter[]; // 根据实际类型定义
  dataSources: DataSource[]; // 根据实际类型定义
  layout: Layout; // 根据实际类型定义
  handleQuerySubmit: (
    values: Record<string, any>,
    files?: Record<string, File[]>
  ) => void;
}

export function DashboardContent({
  title,
  description,
  parameters,
  dataSources,
  layout,
  handleQuerySubmit,
}: DashboardContentProps) {
  return (
    <div className='flex-1 overflow-auto'>
      <div className='container max-w-full py-6 px-4 md:px-8 space-y-6'>
        <>
          {/* 参数区域 */}
          <div className='space-y-2'>
            <ParameterQueryArea
              parameters={parameters}
              dataSources={dataSources}
              onSubmit={handleQuerySubmit}
            />
          </div>

          {/* 展示区域 */}

          {layout && layout.items.length > 0 && <LayoutGrid layout={layout} />}
        </>
      </div>
    </div>
  );
}
