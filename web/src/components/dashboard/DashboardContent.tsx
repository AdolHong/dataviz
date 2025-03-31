import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip';
import { ParameterQueryArea } from './ParameterQueryArea';
import { LayoutGrid } from './LayoutGrid';

export default function DashboardContent(
  title: string,
  description: string,
  parameters: any,
  dataSources: any,
  layout: any,
  handleQuerySubmit: any
) {
  return (
    <div className='flex-1 w-0 min-w-0 overflow-auto'>
      <div className='container max-w-full py-6 px-4 md:px-8 space-y-6'>
        // 显示选中的报表
        <>
          <div>
            <div className='space-y-2'>
              <Tooltip>
                <TooltipTrigger>
                  <h1 className='text-2xl font-semibold'>{title}</h1>
                </TooltipTrigger>
                {description && (
                  <TooltipContent>
                    <p>{description}</p>
                  </TooltipContent>
                )}
              </Tooltip>
            </div>
          </div>

          {/* 参数区域 */}
          <div className='space-y-2'>
            <ParameterQueryArea
              parameters={parameters}
              dataSources={dataSources}
              onSubmit={handleQuerySubmit}
            />
          </div>

          {/* 展示区域 */}
          <div className='space-y-4'>
            <div className='flex items-center justify-between'>
              <h2 className='text-lg font-medium'>数据可视化</h2>
            </div>
            {layout && layout.items.length > 0 && (
              <LayoutGrid layout={layout} />
            )}
          </div>
        </>
      </div>
    </div>
  );
}
