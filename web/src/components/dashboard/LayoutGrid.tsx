import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { type Layout, type LayoutItem } from '@/types/models/layout';
import { type Report } from '@/types/models/report';
import { TooltipContent } from '@/components/ui/tooltip';
import { Tooltip, TooltipTrigger } from '@/components/ui/tooltip';
import { useTabsSessionStore } from '@/lib/store/useTabsSessionStore';
import { useEffect, useRef, useState } from 'react';
import { type DataSource } from '@/types/models/dataSource';
import { type Artifact } from '@/types/models/artifact';
import { ArtifactParams } from './ArtifactParams';
import { Button } from '@/components/ui/button';
import { SettingsIcon } from 'lucide-react';
import {
  useTabQueryStatusStore,
  type QueryStatus,
} from '@/lib/store/useTabQueryStatusStore';
import { DataSourceStatus } from '@/lib/store/useTabQueryStatusStore';

interface LayoutGridProps {
  report: Report;
  activeTabId: string;
}

export function LayoutGrid({ report, activeTabId }: LayoutGridProps) {
  if (!report || activeTabId === '') {
    return <></>;
  }

  console.info('hi, layout');
  const [layout, setLayout] = useState<Layout>(report.layout);

  const [dataSources, setDataSources] = useState<DataSource[]>(
    report.dataSources
  );
  const [artifacts, setArtifacts] = useState<Artifact[]>(report.artifacts);

  // zustand: activateTab
  const activeTab = useTabsSessionStore((state) => state.tabs[activeTabId]);

  // zusatand: queryStatus
  const queryStatus = useTabQueryStatusStore((state) =>
    state.getQueryStatusByTabId(activeTabId)
  );

  useEffect(() => {
    setLayout(report.layout);
    setDataSources(report.dataSources);
    setArtifacts(report.artifacts);
  }, [report]);

  return (
    <>
      <h1 className='text-2xl font-bold'>{activeTab.title}</h1>
      <div
        className='grid gap-4 w-full'
        style={{
          gridTemplateColumns: `repeat(${layout.columns}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${layout.rows}, minmax(200px, auto))`,
          gridAutoFlow: 'dense',
        }}
      >
        {layout.items.map((layoutItem) => {
          const artifact = artifacts.find(
            (artifact) => artifact.id === layoutItem.id
          );

          // 遍历dependencies, 并从dataSources中找到对应的dataSource
          const dependentDataSources: string[] = artifact
            ? artifact.dependencies
                .map((dependency) => {
                  const dataSource = dataSources.find(
                    (dataSource) => dataSource.alias === dependency
                  );
                  return dataSource ? dataSource.id : '';
                })
                .filter(Boolean)
            : [];

          const dependentQueryStatus: Record<string, QueryStatus> = Object.keys(
            queryStatus
          )
            .filter((key) => dependentDataSources.includes(key))
            .reduce(
              (acc, key) => {
                acc[key] = queryStatus[key];
                return acc;
              },
              {} as Record<string, QueryStatus>
            );

          return LayoutGridItem(
            layoutItem,
            artifact,
            dependentQueryStatus,
            activeTab.title,
            'todo: description'
          );
        })}
      </div>
    </>
  );
}

// 渲染具体的网格项内容
const LayoutGridItem = (
  layoutItem: LayoutItem,
  artifact: Artifact | undefined,
  dependentQueryStatus: Record<string, QueryStatus>,
  title: string,
  description: string
) => {
  const [showParams, setShowParams] = useState(false);

  console.info('hi, dependentQueryStatus', dependentQueryStatus);

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
        <CardHeader
          key={`layoutItem.id-${layoutItem.id}-card-header`}
          className='h-5 flex items-center justify-between'
        >
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
            {/* 展示dataSources的queryStatus */}
            {Object.values(dependentQueryStatus).map((queryStatus) => (
              <span
                key={`${queryStatus.dataSourceId}-${queryStatus.status}`}
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
            {/* 展示内容 */}
            <div className='flex-1 flex items-center justify-center p-4 min-w-0'>
              <div className='text-muted-foreground text-sm'>
                {/* 如果没有任何依赖，展示暂无内容 */}
                {Object.values(dependentQueryStatus).length === 0 && (
                  <> 暂无内容</>
                )}

                {/* 如果存在依赖，并且所有依赖都成功，展示内容 */}
                {Object.values(dependentQueryStatus).length > 0 &&
                  Object.values(dependentQueryStatus).every(
                    (queryStatus) =>
                      queryStatus.status === DataSourceStatus.SUCCESS
                  ) && (
                    // 如果所有依赖都成功，展示内容
                    <>{title} 内容成功了</>
                  )}

                {/* 如果存在依赖，并且有一个依赖失败，展示失败信息 */}
                {Object.values(dependentQueryStatus).length > 0 &&
                  Object.values(dependentQueryStatus).some(
                    (queryStatus) =>
                      queryStatus.status === DataSourceStatus.ERROR
                  ) && <> 查询失败</>}
              </div>
            </div>

            {/* 展示参数 */}
            {showParams &&
              Object.values(dependentQueryStatus).length > 0 &&
              Object.values(dependentQueryStatus).every(
                (queryStatus) => queryStatus.status === DataSourceStatus.SUCCESS
              ) && <ArtifactParams artifact={artifact} />}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
