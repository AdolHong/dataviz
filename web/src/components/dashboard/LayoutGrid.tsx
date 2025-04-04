import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { type Layout, type LayoutItem } from '@/types/models/layout';
import { type Report } from '@/types/models/report';
import { TooltipContent } from '@/components/ui/tooltip';
import { Tooltip, TooltipTrigger } from '@/components/ui/tooltip';
import { useTabsSessionStore } from '@/lib/store/useTabsSessionStore';
import { useEffect, useState } from 'react';
import { type DataSource } from '@/types/models/dataSource';
import { type Artifact } from '@/types/models/artifact';
import { ArtifactParams } from './ArtifactParams';
import { Button } from '@/components/ui/button';
import { SettingsIcon } from 'lucide-react';

interface LayoutGridProps {
  report: Report;
}

export function LayoutGrid({ report }: LayoutGridProps) {
  if (!report) {
    return <></>;
  }
  const [layout, setLayout] = useState<Layout>(report.layout);
  const [dataSources, setDataSources] = useState<DataSource[]>(
    report.dataSources
  );
  const [artifacts, setArtifacts] = useState<Artifact[]>(report.artifacts);

  useEffect(() => {
    setLayout(report.layout);
    setDataSources(report.dataSources);
    setArtifacts(report.artifacts);
  }, [report]);

  const activeTab = useTabsSessionStore(
    (state) => state.tabs[state.activeTabId]
  );

  return (
    <>
      <h1 className='text-2xl font-bold'>{activeTab?.title}</h1>
      <div
        className='grid gap-4 w-full'
        style={{
          gridTemplateColumns: `repeat(${layout.columns}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${layout.rows}, minmax(200px, auto))`,
          gridAutoFlow: 'dense',
        }}
      >
        {layout.items.map((layoutItem) =>
          renderGridItem(
            layoutItem,
            artifacts.find((artifact) => artifact.id === layoutItem.id),
            // title用tab的
            activeTab.title,
            'todo: description'
          )
        )}
      </div>
    </>
  );
}

// 渲染具体的网格项内容
const renderGridItem = (
  layoutItem: LayoutItem,
  artifact: Artifact | undefined,
  title: string,
  description: string
) => {
  const [showParams, setShowParams] = useState(false);

  useEffect(() => {
    // 判断artifact有没有参数
    if (artifact && artifact.plainParams && artifact.plainParams.length > 0) {
      setShowParams(true);
    }
  }, [layoutItem]);

  if (!artifact) {
    return <div>没有找到对应的artifact</div>;
  }

  // 计算网格项的样式，包括起始位置和跨度
  const itemStyle = {
    gridColumn: `${layoutItem.x + 1} / span ${layoutItem.width}`,
    gridRow: `${layoutItem.y + 1} / span ${layoutItem.height}`,
  };

  return (
    <div key={layoutItem.id} className='min-h-80 max-h-120' style={itemStyle}>
      <Card className='h-full overflow-hidden shadow-sm hover:shadow-md transition-shadow duration-300'>
        <CardHeader className='h-5 flex items-center justify-between'>
          <div>
            <Tooltip>
              <TooltipTrigger>
                <CardTitle className='text-sm font-medium'>{title}</CardTitle>
              </TooltipTrigger>
              {true && (
                <TooltipContent>
                  <p>{description} todo: description</p>
                </TooltipContent>
              )}
            </Tooltip>
          </div>
          <div className='flex space-x-2 items-center'>
            {[1, 2, 3].map((dot) => (
              <span
                key={dot}
                className='w-3 h-3 rounded-full bg-green-500 shadow-sm'
              />
            ))}

            {artifact &&
              artifact.plainParams &&
              artifact.plainParams.length > 0 && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant='ghost'
                      size='icon'
                      className='h-6 w-6'
                      onClick={() => setShowParams(!showParams)}
                    >
                      <SettingsIcon className='h-4 w-4' />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>{showParams ? '隐藏参数' : '显示参数'}</p>
                  </TooltipContent>
                </Tooltip>
              )}
          </div>
        </CardHeader>
        <CardContent className='p-0 h-[calc(100%-3.5rem)]'>
          <div className='flex h-full border-t overflow-hidden'>
            <div className='flex-1 flex items-center justify-center p-4 min-w-0'>
              <div className='text-muted-foreground text-sm'>{title} 内容</div>
            </div>
            {showParams && artifact && <ArtifactParams artifact={artifact} />}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
