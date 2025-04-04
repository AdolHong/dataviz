import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { type Layout, type LayoutItem } from '@/types/models/layout';
import { type Report } from '@/types/models/report';
import { TooltipContent } from '@/components/ui/tooltip';
import { Tooltip, TooltipTrigger } from '@/components/ui/tooltip';
import { useTabsSessionStore } from '@/lib/store/useTabsSessionStore';
import { memo, useEffect, useRef, useState, useMemo, useCallback } from 'react';
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
import React from 'react';
import { constructNow } from 'date-fns';
import { queryStatusColor } from './ParameterQueryArea';
import { DataSourceDialog } from './DataSourceDialog';
import { artifactApi } from '@/api/artifact';
import type {
  ArtifactRequest,
  ArtifactResponse,
} from '@/types/api/aritifactRequest';
import { toast } from 'sonner';
import Plot from 'react-plotly.js';

interface LayoutGridProps {
  report: Report;
  activeTabId: string;
  isEditModalOpen: boolean;
}

export function LayoutGrid({ report, activeTabId }: LayoutGridProps) {
  if (!report || activeTabId === '') {
    return <></>;
  }

  const [layout, setLayout] = useState<Layout>(report.layout);
  const [dataSources, setDataSources] = useState<DataSource[]>(
    report.dataSources
  );
  const [artifacts, setArtifacts] = useState<Artifact[]>(report.artifacts);

  const activeTab = useTabsSessionStore((state) => state.tabs[activeTabId]);
  const queryStatus = useTabQueryStatusStore((state) =>
    state.getQueryStatusByTabId(activeTabId)
  );

  useEffect(() => {
    setLayout(report.layout);
    setDataSources(report.dataSources);
    setArtifacts(report.artifacts);
  }, [report]);

  // 预处理 artifacts 和 dataSources
  const processedItems = useMemo(() => {
    return layout.items.map((layoutItem) => {
      const artifact = report.artifacts.find(
        (artifact) => artifact.id === layoutItem.id
      );

      const dependentDataSources: string[] = artifact
        ? artifact.dependencies
            .map((dependency) => {
              const dataSource = report.dataSources.find(
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

      return {
        layoutItem,
        artifact,
        strDependentQueryStatus: JSON.stringify(dependentQueryStatus),
        title: artifact?.title || '',
        description: 'todo: description',
        report,
      };
    });
  }, [layout.items, report.artifacts, report.dataSources, queryStatus, report]);

  // 渲染函数使用 useCallback
  const renderLayoutGridItem = useCallback(
    (props: {
      layoutItem: LayoutItem;
      artifact: Artifact | undefined;
      strDependentQueryStatus: string;
      title: string;
      description: string;
      report: Report;
    }) => {
      return (
        <LayoutGridItem key={props.layoutItem.id} {...props} report={report} />
      );
    },
    [report]
  );

  return (
    <>
      <div className='flex items-center'>
        <hr className='flex-1 border-t border-gray-200' />
        <span className='mx-4 text-lg font-bold'>展示区域</span>
        <hr className='flex-1 border-t border-gray-200' />
        <hr className='flex-1 border-t border-gray-200' />
      </div>
      <div
        className='grid gap-4 w-full'
        style={{
          gridTemplateColumns: `repeat(${layout.columns}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${layout.rows}, minmax(200px, auto))`,
          gridAutoFlow: 'dense',
        }}
      >
        {processedItems.map((item) => renderLayoutGridItem(item))}
      </div>
    </>
  );
}

interface LayoutGridItemProps {
  layoutItem: LayoutItem;
  artifact: Artifact | undefined;
  strDependentQueryStatus: string | undefined;
  title: string;
  description: string;
  report: Report;
}

// 渲染具体的网格项内容
const LayoutGridItem = React.memo(
  ({
    layoutItem,
    artifact,
    strDependentQueryStatus,
    title,
    description,
    report,
  }: LayoutGridItemProps) => {
    const [showParams, setShowParams] = useState(false);
    const [selectedDataSourceId, setSelectedDataSourceId] = useState<
      string | null
    >(null);
    const [showDataSourceDialog, setShowDataSourceDialog] = useState(false);

    // 为每个参数创建状态
    const [plainParamValues, setPlainParamValues] = useState<
      Record<string, string | string[]>
    >({});
    const [cascaderParamValues, setCascaderParamValues] = useState<
      Record<string, string | string[]>
    >({});

    console.info('hi, layoutItem');
    // console.info('hi, strDependentQueryStatus', strDependentQueryStatus);

    const dependentQueryStatus = JSON.parse(
      strDependentQueryStatus || '{}'
    ) as Record<string, QueryStatus>;

    // console.info('hi, layoutitem');

    useEffect(() => {
      // 判断artifact有没有参数
      if (artifact && artifact.plainParams && artifact.plainParams.length > 0) {
        setShowParams(true);
      }
    }, [layoutItem]);

    // 处理点击数据源按钮事件
    const handleDataSourceClick = (sourceId: string) => {
      setSelectedDataSourceId(sourceId);
      setShowDataSourceDialog(true);
    };

    // 添加查找数据源的函数
    const findDataSource = (sourceId: string): DataSource | null => {
      const dataSource = report.dataSources.find((ds) => ds.id === sourceId);
      return dataSource || null;
    };

    if (!artifact) {
      return <div>没有找到对应的artifact</div>;
    }

    // 计算网格项的样式，包括起始位置和跨度
    const itemStyle = {
      gridColumn: `${layoutItem.x + 1} / span ${layoutItem.width}`,
      gridRow: `${layoutItem.y + 1} / span ${layoutItem.height}`,
    };

    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [artifactResponse, setArtifactResponse] =
      useState<ArtifactResponse | null>(null);

    useEffect(() => {
      if (
        Object.values(dependentQueryStatus).every(
          (queryStatus) => queryStatus.status === DataSourceStatus.SUCCESS
        )
      ) {
        const queryIds = Object.keys(dependentQueryStatus).reduce(
          (acc, key) => {
            const source = findDataSource(key);
            acc[source?.alias || ''] =
              dependentQueryStatus[key].queryResponse?.data.uniqueId || '';
            return acc;
          },
          {} as Record<string, string>
        );
        executeArtifact(artifact, queryIds);
      }
    }, [strDependentQueryStatus, plainParamValues, cascaderParamValues]);

    // 执行artifact的函数
    const executeArtifact = async (
      artifact: Artifact,
      queryIds: Record<string, string>
    ) => {
      setIsLoading(true);
      setError(null);

      try {
        // 构建请求参数
        const request: ArtifactRequest = {
          uniqueId: `artifact_${artifact.id}_${Date.now()}`,
          dfAliasUniqueIds: queryIds,
          plainParamValues: {}, // 可以从UI收集参数
          cascaderParamValues: {}, // 可以从UI收集参数
          pyCode: artifact.code,
          engine: artifact.executor_engine,
        };

        // 调用API
        const response = await artifactApi.executeArtifact(request);
        setArtifactResponse(response);
        console.info('hi, response', response);

        // 处理返回结果
        if (response.status === 'success') {
        } else {
          toast.error(response.error || '执行失败');
          setError(response.error || '执行失败');
        }
      } catch (err) {
        // 错误处理
        const errorMessage =
          err instanceof Error ? err.message : '请求过程中发生错误';
        setError(errorMessage);
        console.error('执行artifact失败:', err);
        return null;
      } finally {
        setIsLoading(false);
      }
    };

    const renderArtifactData = (artifactData: ArtifactResponse) => {
      if (!artifactData.dataContext) {
        return <div>无数据</div>;
      }

      console.info('hi, artifactData', artifactData);

      switch (artifactData.dataContext.type) {
        case 'text':
          return (
            <pre className='whitespace-pre-wrap'>
              {artifactData.dataContext.data}
            </pre>
          );

        case 'table':
          return (
            <div
              className='w-full overflow-x-auto'
              dangerouslySetInnerHTML={{
                __html: artifactData.dataContext.data,
              }}
            />
          );

        case 'image':
          return (
            <img
              src={`data:image/png;base64,${artifactData.dataContext.data}`}
              alt='Artifact Image'
              className='max-w-full max-h-full object-contain'
            />
          );

        case 'plotly':
          const { data, layout, config, frames } = JSON.parse(
            artifactData.dataContext.data
          );

          return (
            <div className='w-full h-full flex'>
              <Plot
                data={data}
                layout={{
                  ...layout,
                  autosize: true,
                  width: undefined,
                  height: 300,
                  margin: { l: 50, r: 50, b: 50, t: 50, pad: 4 },
                  font: { family: 'Arial, sans-serif' },
                  responsive: true,
                }}
                frames={frames}
                config={{
                  ...(config || {}),
                  responsive: true,
                  displayModeBar: true,
                  displaylogo: false,
                  modeBarButtonsToRemove: ['lasso2d', 'select2d'],
                }}
                style={{ width: '100%', height: '100%' }}
              />
            </div>
          );

        case 'echart':
          return (
            <div
              id='echart-container'
              data-echart={artifactData.dataContext.data}
              className='w-full h-full'
            >
              EChart图表渲染位置
            </div>
          );

        case 'altair':
          return (
            <div
              id='altair-container'
              data-altair={artifactData.dataContext.data}
              className='w-full h-full'
            >
              Altair图表渲染位置
            </div>
          );

        default:
          return <div>不支持的数据类型</div>;
      }
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
              {/* 修改为按钮，点击可查看数据源详情 */}
              {Object.entries(dependentQueryStatus).map(
                ([sourceId, status]) => (
                  <button
                    key={`${sourceId}-${status.status}`}
                    onClick={() => handleDataSourceClick(sourceId)}
                    className={`w-3 h-3 rounded-full cursor-pointer ${queryStatusColor(
                      status.status
                    )}`}
                  />
                )
              )}

              {(artifact &&
                artifact.plainParams &&
                artifact.plainParams.length > 0) ||
                (artifact.cascaderParams &&
                  artifact.cascaderParams.length > 0 && (
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
                  ))}
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
                      <div>
                        {isLoading && <div>加载中...</div>}
                        {error && <div className='text-red-500'>{error}</div>}
                        {!isLoading &&
                          !error &&
                          artifactResponse &&
                          artifactResponse.dataContext && (
                            <div className='w-full h-full flex'>
                              {renderArtifactData(artifactResponse)}
                            </div>
                          )}
                      </div>
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
                  (queryStatus) =>
                    queryStatus.status === DataSourceStatus.SUCCESS
                ) && (
                  <ArtifactParams
                    artifact={artifact}
                    dataSources={report.dataSources}
                    dependentQueryStatus={dependentQueryStatus}
                    // plainParamValues={plainParamValues}
                    // setPlainParamValues={setPlainParamValues}
                    // cascaderParamValues={cascaderParamValues}
                    // setCascaderParamValues={setCascaderParamValues}
                  />
                )}
            </div>
          </CardContent>

          {/* 添加DataSourceDialog组件 */}
          {showDataSourceDialog && selectedDataSourceId && (
            <DataSourceDialog
              open={showDataSourceDialog}
              onOpenChange={setShowDataSourceDialog}
              dataSource={findDataSource(selectedDataSourceId)}
              queryStatus={dependentQueryStatus[selectedDataSourceId] || null}
            />
          )}
        </Card>
      </div>
    );
  }
);
