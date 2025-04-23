import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { type LayoutItem } from '@/types/models/layout';
import { type Report } from '@/types/models/report';
import { TooltipContent } from '@/components/ui/tooltip';
import { Tooltip, TooltipTrigger } from '@/components/ui/tooltip';
import { memo, useEffect, useRef, useState, useMemo } from 'react';
import { type DataSource } from '@/types/models/dataSource';
import { type Artifact } from '@/types/models/artifact';
import { LayoutItemParams } from './LayoutItemParams';
import { Button } from '@/components/ui/button';
import { SettingsIcon, Copy } from 'lucide-react';
import { type QueryStatus } from '@/lib/store/useQueryStatusStore';
import { DataSourceStatus } from '@/lib/store/useQueryStatusStore';
import React from 'react';
import { queryStatusColor } from './ParameterQueryArea';
import { DataSourceDialog } from './DataSourceDialog';
import { ArtifactResponseDialog } from './ArtifactResponseDialog';
import { artifactApi } from '@/api/artifact';
import { parseDynamicDate } from '@/utils/parser';
import type {
  ArtifactRequest,
  ArtifactResponse,
  PlainParamValue,
} from '@/types/api/aritifactRequest';
import { toast } from 'sonner';
import Plot from 'react-plotly.js';
import * as echarts from 'echarts';
import { VegaLite } from 'react-vega';
import dayjs from 'dayjs';
import { ArtifactTableView } from '@/components/ArtifactTableView';

// Artifact状态颜色
export const artifactStatusColor = (status: string): string => {
  switch (status) {
    case 'success':
      return 'bg-green-300 hover:bg-green-500 opacity-60 hover:opacity-100';
    case 'error':
      return 'bg-red-500 hover:bg-red-600';
    default:
      return 'bg-gray-300 hover:bg-gray-400  opacity-60 hover:opacity-100';
  }
};

interface LayoutGridItemProps {
  layoutItem: LayoutItem;
  artifact: Artifact | undefined;
  report: Report;
  strDependentQueryStatus: string;
}

export const LayoutGridItem = memo(
  ({
    layoutItem,
    artifact,
    report,
    strDependentQueryStatus,
  }: LayoutGridItemProps) => {
    if (!artifact || !report) {
      return <div>没有找到对应的artifact</div>;
    }
    // todo: 默认是否展示参数
    const [showParams, setShowParams] = useState(
      (artifact &&
        ((artifact.plainParams && artifact.plainParams.length > 0) ||
          (artifact.inferredParams && artifact.inferredParams.length > 0) ||
          (artifact.cascaderParams && artifact.cascaderParams.length > 0))) ||
        false
    );
    const [showDataSourceDialog, setShowDataSourceDialog] = useState(false);
    const [selectedDataSourceId, setSelectedDataSourceId] = useState<
      string | null
    >(null);
    const [showArtifactDialog, setShowArtifactDialog] = useState(false);
    const [isInitialized, setIsInitialized] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [artifactResponse, setArtifactResponse] =
      useState<ArtifactResponse | null>(null);

    // 为每个参数创建状态
    const [plainParamValues, setPlainParamValues] = useState<
      Record<string, PlainParamValue>
    >({});
    const [cascaderParamValues, setCascaderParamValues] = useState<
      Record<string, string | string[]>
    >({});
    const [plainParamChoices, setPlainParamChoices] = useState<
      Record<string, Record<string, string>[]>
    >({});

    // 在useState区域添加inferredParams相关状态
    const [inferredParamValues, setInferredParamValues] = useState<
      Record<string, string[]>
    >({});
    const [inferredParamChoices, setInferredParamChoices] = useState<
      Record<string, Record<string, string>[]>
    >({});

    const dependentQueryStatus = useMemo(
      () =>
        JSON.parse(strDependentQueryStatus || '{}') as Record<
          string,
          QueryStatus
        >,
      [strDependentQueryStatus]
    );

    // 处理点击数据源按钮事件
    const handleDataSourceClick = (sourceId: string) => {
      setSelectedDataSourceId(sourceId);
      setShowDataSourceDialog(true);
    };

    // 处理点击Artifact按钮事件
    const handleArtifactClick = () => {
      setShowArtifactDialog(true);
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

    useEffect(() => {
      // 处理plainParams的初始化
      artifact.plainParams?.forEach((param) => {
        // 先处理choices的动态日期
        const choices = param.choices.map((choice) => ({
          key: parseDynamicDate(choice.key),
          value: parseDynamicDate(choice.value),
        }));

        setPlainParamChoices((prev) => ({
          ...prev,
          [param.name]: choices,
        }));

        // 再处理default
        if (param.type === 'single') {
          const defaulVal = parseDynamicDate(param.default);
          setPlainParamValues((prev) => ({
            ...prev,
            [param.name]: {
              name: param.name,
              type: 'single',
              valueType: param.valueType,
              value: defaulVal,
            },
          }));
        } else if (param.type === 'multiple') {
          const defaulVal = param.default.map((val) => parseDynamicDate(val));
          setPlainParamValues((prev) => ({
            ...prev,
            [param.name]: {
              name: param.name,
              type: 'multiple',
              valueType: param.valueType,
              value: defaulVal,
            },
          }));
        }
      });

      // 处理inferredParams的初始化
      const inferredChoices: Record<string, Record<string, string>[]> = {};

      // 从每个查询响应中获取inferredContext并更新inferredParamChoices
      Object.values(dependentQueryStatus).forEach((queryStatus) => {
        if (queryStatus.queryResponse?.inferredContext) {
          const { inferred } = queryStatus.queryResponse.inferredContext;
          if (inferred) {
            // 遍历每个推断参数
            artifact?.inferredParams?.forEach((param) => {
              // const paramKey = `${param.dfAlias}_${param.dfColumn}_${param.id}`;
              // 查找对应数据源和列的值
              const paramKey = `${param.dfAlias}.${param.dfColumn}`;
              if (inferred[paramKey] && inferred[paramKey].length > 0) {
                inferredChoices[paramKey] = inferred[paramKey].map((value) => ({
                  key: String(value),
                  value: String(value),
                }));
              }
            });
          }
        }
      });

      // 更新推断参数选项
      if (Object.keys(inferredChoices).length > 0) {
        setInferredParamChoices(inferredChoices);
      }

      // ps: 有了isInitialized, 可以避免在无参数的artifact请求多次画图;
      setIsInitialized(true);
    }, [report]);

    useEffect(() => {
      // 条件1: 组件已经初始化完了, 即useEffect[report];
      if (!isInitialized || !dependentQueryStatus || !report) {
        return;
      }

      if (
        // 条件1: 所有状态均成功,  且queryStatus查询时间大于report的更新时间
        Object.values(dependentQueryStatus).length > 0 &&
        Object.values(dependentQueryStatus).every(
          (queryStatus) => queryStatus.status === DataSourceStatus.SUCCESS
        ) &&
        // 条件2: 所有queryStatus的queryTime大于report的updatedAt
        report.updatedAt &&
        Object.values(dependentQueryStatus).every(
          (queryStatus) =>
            queryStatus.queryResponse &&
            // 日期比较，用了dayjs
            dayjs(queryStatus.queryResponse.queryTime).isAfter(
              dayjs(report.updatedAt)
            )
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
    }, [
      dependentQueryStatus,
      plainParamValues,
      cascaderParamValues,
      inferredParamValues,
      isInitialized,
    ]);

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
          plainParamValues: plainParamValues, // 可以从UI收集参数
          cascaderParamValues: cascaderParamValues, // 可以从UI收集参数
          inferredParamValues: inferredParamValues, // 添加推断参数值
          pyCode: artifact.code,
          engine: artifact.executor_engine,
        };
        console.info('request', request);

        // 调用API
        const response = await artifactApi.executeArtifact(request);
        setArtifactResponse(response);

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
        return null;
      } finally {
        setIsLoading(false);
      }
    };

    const renderArtifactData = (artifactData: ArtifactResponse) => {
      if (!artifactData.dataContext) {
        return <div>无数据</div>;
      }
      switch (artifactData.dataContext.type) {
        case 'text':
          return (
            <pre className='whitespace-pre-wrap'>
              {artifactData.dataContext.data}
            </pre>
          );

        case 'table':
          return <ArtifactTableView data={artifactData.dataContext.data} />;
        case 'image':
          return (
            <div className='w-[95%] h-[95%] flex justify-center items-center'>
              <img
                src={`data:image/png;base64,${artifactData.dataContext.data}`}
                alt='Artifact Image'
                className='max-w-full max-h-[300px] object-contain'
              />
            </div>
          );

        case 'plotly':
          const { data, layout, config, frames } = JSON.parse(
            artifactData.dataContext.data
          );

          return (
            <div className='w-[95%] h-[95%] flex justify-center items-center'>
              <Plot
                data={data}
                layout={{
                  ...layout,
                  autosize: true,
                  height: 300,
                  margin: { l: 20, r: 20, b: 50, t: 50, pad: 4 },
                  font: { family: 'Arial, sans-serif' },
                  sliders: layout.sliders, // 确保滑块配置被传递
                  modebar: {
                    orientation: 'v',
                  },
                }}
                frames={frames} // 明确传递动画帧
                config={{
                  ...(config || {}),
                  responsive: true,
                  // displayModeBar: 'hover',
                  displaylogo: false,
                  // displayModeBar: false,
                  modeBarButtonsToRemove: [
                    'lasso2d',
                    'select2d',
                    'zoom2d',
                    'toImage',
                    'pan2d',
                    'resetScale2d',
                  ],
                }}
                style={{ width: '100%', height: '100%' }}
              />
            </div>
          );

        case 'echart':
          return (
            <EChartComponent
              optionData={artifactData.dataContext.data}
              showParams={showParams}
            />
          );

        case 'altair':
          return (
            <div className='w-[95%] h-[95%] flex justify-center items-center'>
              <VegaChart data={artifactData.dataContext.data} />
            </div>
          );

        default:
          return (
            <div className='w-[95%] h-[95%] flex justify-center items-center'>
              <div>不支持的数据类型</div>
            </div>
          );
      }
    };

    // 添加一个安全的复制函数
    const safeCopyToClipboard = async (content: string) => {
      // 检查 Clipboard API 是否可用
      if (
        navigator?.clipboard &&
        navigator?.clipboard?.writeText &&
        typeof navigator?.clipboard?.writeText === 'function'
      ) {
        try {
          await navigator.clipboard.writeText(content);
          return true;
        } catch {
          return false;
        }
      }

      // 备选方案：使用 document.execCommand
      try {
        const textArea = document.createElement('textarea');
        textArea.value = content;
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        document.body.appendChild(textArea);
        textArea.select();

        const successful = document.execCommand('copy');
        document.body.removeChild(textArea);
        return successful;
      } catch {
        return false;
      }
    };

    // 修改现有的复制逻辑
    const handleCopyContent = async () => {
      if (!artifact || !artifactResponse) {
        return;
      }

      const queryIds = Object.keys(dependentQueryStatus).reduce(
        (acc, key) => {
          const source = findDataSource(key);
          acc[source?.alias || ''] =
            dependentQueryStatus[key].queryResponse?.data.uniqueId || '';
          return acc;
        },
        {} as Record<string, string>
      );

      // 准备请求参数，根据executeArtifact函数中的构建方式
      const request: ArtifactRequest = {
        uniqueId: `artifact_${artifact.id}_${Date.now()}`,
        dfAliasUniqueIds: queryIds,
        plainParamValues: plainParamValues || {},
        cascaderParamValues: cascaderParamValues || {},
        inferredParamValues: inferredParamValues || {}, // 添加推断参数值
        pyCode: artifact.code,
        engine: artifact.executor_engine,
      };

      // 调用新API
      const response = await artifactApi.getArtifactCode(request);
      console.info('response', response);

      // 如果不能获取到代码，则提示
      if (!response || !response.pyCode) {
        toast.error('没有获取到代码');
        return;
      }
      const content = response.pyCode;

      // 复制到剪贴板或尝试下载
      try {
        const copySuccess = await safeCopyToClipboard(content);

        if (copySuccess) {
          toast.success('已复制到剪切板');
        } else {
          // 复制失败，尝试下载文件
          const blob = new Blob([content], { type: 'text/plain' });
          const downloadLink = document.createElement('a');
          downloadLink.href = URL.createObjectURL(blob);
          downloadLink.download = 'artifact_code.py';

          document.body.appendChild(downloadLink);
          downloadLink.click();
          document.body.removeChild(downloadLink);

          URL.revokeObjectURL(downloadLink.href);
          toast.info('复制失败，已为您下载文件');
        }
      } catch (err) {
        toast.error('复制和下载均失败', {
          description: err instanceof Error ? err.message : '未知错误',
        });
      }
    };

    return (
      <div key={layoutItem.id} style={itemStyle}>
        <Card className='h-full flex overflow-hidden shadow-sm hover:shadow-md transition-shadow duration-300  mt-0 mb-0 py-1 gap-0'>
          <CardHeader
            key={`layoutItem.id-${layoutItem.id}-card-header`}
            className='h-10 flex items-center justify-between border-b-1 shadow-sm'
          >
            <div>
              <Tooltip>
                <TooltipTrigger>
                  <CardTitle className='text-sm font-medium'>
                    {artifact.title}
                  </CardTitle>
                </TooltipTrigger>
                {true && (
                  <TooltipContent>
                    <p>{artifact.dependencies}</p>
                  </TooltipContent>
                )}
              </Tooltip>
            </div>

            <div className='flex space-x-2 items-center'>
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
              {/* 执行按钮 */}
              {
                <button
                  className={`w-3 h-3 aspect-square cursor-pointer ${artifactStatusColor(
                    artifactResponse?.status || ''
                  )}`}
                  onClick={handleArtifactClick}
                />
              }
              {/* 复制剪切板按钮 */}
              {
                <button
                  className='w-3 h-3 aspect-square cursor-pointer'
                  onClick={async () => {
                    if (artifact && artifactResponse) {
                      await handleCopyContent();
                    }
                  }}
                >
                  <Copy className='w-full h-full text-gray-500 hover:text-gray-700' />
                </button>
              }

              {/* 展示参数按钮 */}
              {artifact &&
                ((artifact.plainParams && artifact.plainParams.length > 0) ||
                  (artifact.cascaderParams &&
                    artifact.cascaderParams.length > 0) ||
                  (artifact.inferredParams &&
                    artifact.inferredParams.length > 0)) && (
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
          <CardContent className='flex flex-1 border-t overflow-hidden p-4  items-center justify-center text-muted-foreground text-sm'>
            {/* 展示内容 */}
            {Object.values(dependentQueryStatus).length === 0 && <> 暂无内容</>}

            {Object.values(dependentQueryStatus).length > 0 &&
              Object.values(dependentQueryStatus).every(
                (queryStatus) => queryStatus.status === DataSourceStatus.SUCCESS
              ) && (
                <div className='w-full h-full'>
                  {isLoading && <div>加载中...</div>}
                  {error && <div className='text-red-500'>{error}</div>}
                  {!isLoading &&
                    !error &&
                    artifactResponse &&
                    artifactResponse.dataContext && (
                      <>{renderArtifactData(artifactResponse)}</>
                    )}
                </div>
              )}

            {Object.values(dependentQueryStatus).length > 0 &&
              Object.values(dependentQueryStatus).some(
                (queryStatus) => queryStatus.status === DataSourceStatus.ERROR
              ) && <> 查询失败</>}
          </CardContent>

          {/* 展示参数 */}
          <div className={`${showParams ? 'block' : 'hidden'}`}>
            <LayoutItemParams
              artifact={artifact}
              dataSources={report.dataSources}
              dependentQueryStatus={dependentQueryStatus}
              plainParamValues={plainParamValues}
              setPlainParamValues={setPlainParamValues}
              setCascaderParamValues={setCascaderParamValues}
              plainParamChoices={plainParamChoices}
              setPlainParamChoices={setPlainParamChoices}
              inferredParamChoices={inferredParamChoices}
              inferredParamValues={inferredParamValues}
              setInferredParamValues={setInferredParamValues}
            />
          </div>

          {/* 添加DataSourceDialog组件 */}
          {showDataSourceDialog && selectedDataSourceId && (
            <DataSourceDialog
              open={showDataSourceDialog}
              onOpenChange={setShowDataSourceDialog}
              dataSource={findDataSource(selectedDataSourceId)}
              queryStatus={dependentQueryStatus[selectedDataSourceId] || null}
            />
          )}

          {/* 添加ArtifactResponseDialog组件 */}
          {showArtifactDialog && artifactResponse && (
            <ArtifactResponseDialog
              open={showArtifactDialog}
              onOpenChange={setShowArtifactDialog}
              artifact={artifact}
              artifactResponse={artifactResponse}
            />
          )}
        </Card>
      </div>
    );
  }
);

// ECharts 图表渲染组件
interface EChartComponentProps {
  optionData: string; // JSON 字符串格式的 ECharts 配置
  showParams: boolean;
}

const EChartComponent: React.FC<EChartComponentProps> = ({
  optionData,
  showParams,
}) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    let parsedOption: echarts.EChartsOption;
    try {
      parsedOption = JSON.parse(optionData);
    } catch (e) {
      console.error('Failed to parse ECharts option data:', e);
      // 可以在这里显示错误提示，或者渲染一个占位符
      return; // 解析失败则不继续
    }

    // 初始化或更新图表
    if (chartRef.current) {
      // 如果实例不存在或已销毁，则初始化
      if (!chartInstance.current || chartInstance.current.isDisposed()) {
        chartInstance.current = echarts.init(chartRef.current);
      }

      // 设置配置项
      chartInstance.current.setOption(parsedOption, true); // true 表示不合并，完全替换
    }

    // 添加窗口大小调整监听器
    const handleResize = () => {
      if (chartInstance.current && !chartInstance.current.isDisposed()) {
        chartInstance.current.resize();
      }
    };

    window.addEventListener('resize', handleResize);

    // 清理函数：组件卸载时销毁图表实例并移除监听器
    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartInstance.current && !chartInstance.current.isDisposed()) {
        chartInstance.current.dispose();
        chartInstance.current = null; // 清空引用
      }
    };
  }, [optionData, showParams]); // 当配置数据变化时，重新执行 effect

  console.info('charRef', chartRef);

  // 返回用于挂载 ECharts 的 div
  return (
    <div
      ref={chartRef}
      style={{
        width: '100%',
        height: '300px',
      }}
    />
  );
};

const VegaChart: React.FC<{ data: string }> = ({ data }) => {
  const [chartData, _] = useState(JSON.parse(data));
  if (!chartData) return <div>Loading...</div>;

  console.info('chartData', chartData);

  // const { view } = chartData['config'];

  const newChartData = {
    ...chartData,
    // autosize: { type: 'fit', contains: 'padding' },
  };

  return <VegaLite spec={newChartData} />;
};
