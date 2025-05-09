import React, { useState, useEffect, memo, useCallback } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { X, ChevronUp, ChevronDown, Upload, Search } from 'lucide-react';
import { type Parameter } from '@/types/models/parameter';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { FileUploadArea } from '@/components/dashboard/FileUploadArea';
import type { Artifact, DataSource } from '@/types';
import { toast } from 'sonner';
import { DatePicker } from '@/components/ui/datepicker';
import { Card } from '../ui/card';
import { CardContent } from '../ui/card';
import {
  type DatePickerParamConfig,
  type DateRangePickerParamConfig,
} from '@/types/models/parameter';
import dayjs from 'dayjs';
import {
  useTabFilesStore,
  type FileCache,
} from '@/lib/store/useFileSessionStore';

import { DataSourceStatus } from '@/lib/store/useQueryStatusStore';

import { parseDynamicDate, replaceParametersInCode } from '@/utils/parser';
import {
  useQueryStatusStore,
  type QueryStatus,
} from '@/lib/store/useQueryStatusStore';
import { useParamValuesStore } from '@/lib/store/useParamValuesStore';
import { useSessionIdStore } from '@/lib/store/useSessionIdStore';
import { queryApi } from '@/api/query';
import { Combobox } from '../combobox';
import type { QueryRequest } from '@/types/api/queryRequest';
import { DateRangePicker } from '@/components/ui/daterangepicker';

import { useDataSourceDialogStore } from '@/lib/store/useDataSourceDialogStore';

interface ParameterQueryAreaProps {
  activeTabId: string;
  reportId: string;
  reportUpdatedAt: string;
  parameters?: Parameter[];
  dataSources?: DataSource[];
  artifacts?: Artifact[];
  onEditReport: () => void;
}

export const ParameterQueryArea = memo(
  ({
    activeTabId,
    reportId,
    reportUpdatedAt,
    parameters,
    dataSources,
    artifacts,
    onEditReport,
  }: ParameterQueryAreaProps) => {
    console.info('hi, parameterQueryArea');

    const { getSessionId } = useSessionIdStore();
    const [parametersExpanded, setParametersExpanded] = useState(true);

    const openDataSourceDialog = useDataSourceDialogStore(
      (state) => state.openDialog
    );

    // 当前标签: parameters or upload
    const [activeParameterTab, setActiveParameterTab] = useState('parameters');
    const [isQuerying, setIsQuerying] = useState(false);

    // 表单
    const [values, setValues] = useState<Record<string, any>>({});
    const [files, setFiles] = useState<Record<string, FileCache>>({});

    const [nameToChoices, setNameToChoices] = useState<
      Record<string, Record<string, string>[]>
    >({});

    // zustand: values, setValues
    const setTabIdParamValues = useParamValuesStore(
      (state) => state.setTabIdParamValues
    );
    const cachedValues: Record<string, any> = useParamValuesStore((state) =>
      state.getTabIdParamValues(activeTabId)
    );
    const setCachedValues = useCallback(
      (values: Record<string, any>) => setTabIdParamValues(activeTabId, values),
      [activeTabId, setTabIdParamValues]
    );

    // zustand: files, setFiles
    const setTabIdFiles = useTabFilesStore((state) => state.setTabIdFiles);
    const cachedFiles: Record<string, FileCache> = useTabFilesStore((state) =>
      state.getTabIdFiles(activeTabId)
    );
    const setCachedFiles = useCallback(
      (files: Record<string, FileCache>) => setTabIdFiles(activeTabId, files),
      [activeTabId, setTabIdFiles]
    );

    // zustand: queryStatus, setQueryStatus
    const setQueryStatusByTabIdAndSourceId = useQueryStatusStore(
      (state) => state.setQueryStatusByTabIdAndSourceId
    );
    const setQueryStatus = useCallback(
      (sourceId: string, status: QueryStatus) =>
        setQueryStatusByTabIdAndSourceId(activeTabId, sourceId, status),
      [activeTabId, setQueryStatusByTabIdAndSourceId]
    );

    const queryStatus = useQueryStatusStore((state) =>
      state.getQueryStatusByTabId(activeTabId)
    );

    // 检查需要文件上传的数据源
    const csvDataSources =
      dataSources?.filter(
        (ds) =>
          ds.executor.type === 'csv_uploader' || ds.executor.type === 'csv_data'
      ) || [];
    const requireFileUpload = csvDataSources.length > 0;

    // 使用 useEffect 在初始渲染时设置默认值
    useEffect(() => {
      console.info('hi, parameterQueryArea[2nd 初始化参数] ');

      // 若values为空, 初始化参数值
      initiateValues();

      // 初始化选项
      initialChoices();

      // 初始化文件
      initialFiles();
    }, [parameters]);

    const initiateValues = () => {
      // if (values && Object.keys(values).length > 0) {
      //   return;
      // }
      const initValues: Record<string, any> = {};
      parameters?.forEach((param) => {
        // 对于多选和多输入类型，使用默认数组
        if (
          param.config.type === 'multi_select' ||
          param.config.type === 'multi_input'
        ) {
          const defaultVal = param.config.default || [];
          const parsedVal = defaultVal.map((val: string) =>
            parseDynamicDate(val)
          );
          initValues[param.name] = parsedVal;
        }
        // 对于日期范围选择器，处理两个日期值
        else if (param.config.type === 'date_range_picker') {
          const defaultVal = param.config.default || ['', ''];
          const parsedVal = defaultVal.map((val: string) =>
            parseDynamicDate(val)
          );
          initValues[param.name] = parsedVal;
        }
        // 对于单选和单输入类型，使用默认值
        else if (
          param.config.type === 'single_select' ||
          param.config.type === 'single_input' ||
          param.config.type === 'date_picker'
        ) {
          const defaultVal = param.config.default;
          const parseVal = parseDynamicDate(defaultVal);
          initValues[param.name] = parseVal;
        }
      });

      const updatedValues = { ...initValues, ...cachedValues };
      setValues(updatedValues);
    };

    const initialChoices = () => {
      parameters?.forEach((param) => {
        if (
          param.config.type === 'single_select' ||
          param.config.type === 'multi_select'
        ) {
          const choices: Record<string, string>[] = param.config.choices;
          const newChoices = choices.map((choice) => {
            return {
              key: choice.key,
              value: parseDynamicDate(choice.value),
            };
          });

          nameToChoices[param.name] = newChoices;
        }
      });
      setNameToChoices(nameToChoices);
    };

    const initialFiles = () => {
      // 若有缓存文件，则加载
      csvDataSources.forEach((ds) => {
        if (cachedFiles[ds.id]) {
          files[ds.id] = cachedFiles[ds.id];
        }
      });
    };

    // 修改handleQuerySubmit函数，接收文件参数为对象
    const handleQuerySubmit = async () => {
      if (dataSources && dataSources.length > 0) {
        setCachedValues(values);
        setCachedFiles(files);

        // 重新初始化状态
        setIsQuerying(true);
        dataSources.map((dataSource) => {
          // 初始化QueryStatus的状态
          const newStatus: QueryStatus = {
            status: DataSourceStatus.INIT,
          };
          setQueryStatus(dataSource.id, newStatus);
        });

        // 发起query请求
        const promises = dataSources.map((dataSource) => {
          return handleQueryRequest(dataSource);
        });
        // 过滤掉 null，并等待请求结果
        await Promise.all(promises.filter((promise) => promise !== null));
        setIsQuerying(false);
      }
    };

    const constructQueryRequest = (
      dataSource: DataSource
    ): QueryRequest | null => {
      // sessionId + tabId + dataSourceId (标识此处请求是唯一的)
      const uniqueId = getSessionId() + '_' + activeTabId + '_' + dataSource.id;

      // cascader context: 级联参数
      let cascaderRequired: string[] = [];
      artifacts?.forEach((artifact) => {
        artifact?.cascaderParams?.forEach((cascaderParam) => {
          if (cascaderParam.dfAlias === dataSource.alias) {
            let cascaderTuple: string[] = [];
            cascaderParam.levels.forEach((level) => {
              cascaderTuple.push(level.dfColumn);
            });
            cascaderRequired.push(JSON.stringify(cascaderTuple));
          }
        });
      });

      // inferred context: 推断参数
      let inferredRequired: string[] = [];
      artifacts?.forEach((artifact) => {
        artifact.inferredParams?.forEach((inferredParam) => {
          if (inferredParam.dfAlias === dataSource.alias) {
            inferredRequired.push(
              `${inferredParam.dfAlias}.${inferredParam.dfColumn}`
            );
          }
        });
      });

      // request context
      let requestContext = null;
      if (dataSource.executor.type === 'sql') {
        const code = replaceParametersInCode(
          dataSource.executor.code,
          values,
          parameters || []
        );
        requestContext = {
          type: 'sql',
          engine: dataSource.executor.engine,
          code: dataSource.executor.code,
          parsedCode: code,
          paramValues: values,
        };
      } else if (dataSource.executor.type === 'python') {
        const code = replaceParametersInCode(
          dataSource.executor.code,
          values,
          parameters || []
        );
        requestContext = {
          type: 'python',
          engine: dataSource.executor.engine,
          code: dataSource.executor.code,
          parsedCode: code,
          paramValues: values,
        };
      } else if (dataSource.executor.type === 'csv_uploader') {
        requestContext = {
          type: 'csv_uploader',
          dataContent: files[dataSource.id]?.fileContent || '',
        };
      } else if (dataSource.executor.type === 'csv_data') {
        requestContext = {
          type: 'csv_data',
        };
      }

      console.info('sourceID, required:', dataSource.id, inferredRequired);
      const queryRequest = {
        uniqueId: uniqueId,

        requestContext: {
          fileId: reportId,
          sourceId: dataSource.id,
          reportUpdateTime: reportUpdatedAt,
          ...requestContext,
        },
        cascaderContext: {
          required: cascaderRequired,
        },
        inferredContext: {
          required: inferredRequired,
        },
      } as QueryRequest;

      return queryRequest;
    };

    const handleQueryRequest = async (dataSource: DataSource) => {
      const queryRequest = constructQueryRequest(dataSource);

      if (!queryRequest) {
        toast.error(
          `[查询失败] ${dataSource.id}(${dataSource.name}), 不支持的查询类型`
        );
        return null;
      }
      const response = await queryApi.executeQueryBySourceId(queryRequest);

      // 查询结果
      let newStatus: QueryStatus = {
        status:
          response.status === 'success'
            ? DataSourceStatus.SUCCESS
            : DataSourceStatus.ERROR,
        queryResponse: response,
      };
      setQueryStatus(dataSource.id, newStatus);

      if (response.alerts.length > 0 && response.status !== 'success') {
        response.alerts.forEach((alert) => {
          toast.info(`[${alert.type}] ${alert.message}`);
        });
      } else {
        toast.info(`[查询] ${dataSource.name}(${dataSource.id}): 成功`);
        return response;
      }
    };

    const toggleParametersExpanded = () => {
      setParametersExpanded(!parametersExpanded);
    };

    const handleValueChange = (name: string, value: any) => {
      const newValues = { ...values, [name]: value };
      setValues(newValues);
    };

    const handleSubmit = (e: React.FormEvent) => {
      e.preventDefault();

      if (!activeTabId) {
        toast.error('请先打开一个标签页');
        return;
      }
      if (
        requireFileUpload &&
        Object.keys(files).length !==
          csvDataSources.filter((ds) => ds.executor.type === 'csv_uploader')
            .length
      ) {
        toast.error('请上传文件');
        return;
      }

      if (dataSources?.length === 0) {
        toast.error('请先添加数据源');
        return;
      }

      if (artifacts?.length === 0) {
        toast.error('请先添加图表');
        return;
      }

      // 暂时保留这份代码，不确定要不要拦截
      // // 检查日期范围是否合理
      // const isDateRangeValid = parameters?.every((param) => {
      //   console.info('param', param);
      //   console.info('values[param.name]', values[param.name]);

      //   if (
      //     param.config.type === 'date_range_picker' &&
      //     !(
      //       Array.isArray(values[param.name]) &&
      //       values[param.name].length === 2 &&
      //       values[param.name][0] !== '' &&
      //       values[param.name][1] !== ''
      //     )
      //   ) {
      //     toast.error(`[${param.name}] 请选择日期范围`);
      //     return false;
      //   }
      //   return true;
      // });
      // if (!isDateRangeValid) {
      //   return;
      // }

      handleQuerySubmit();
    };

    // 多输入框键盘事件处理
    const handleMultiInputKeyDown = (
      e: React.KeyboardEvent<HTMLInputElement>,
      param: Parameter
    ) => {
      if (e.key === 'Enter' && e.currentTarget.value.trim() !== '') {
        e.preventDefault();
        const newValue = e.currentTarget.value.trim();
        const currentValues = values[param.name] || [];

        // 检查是否已存在该值
        if (!currentValues.includes(newValue)) {
          handleValueChange(param.name, [...currentValues, newValue]);
          e.currentTarget.value = '';
        } else {
          // 可选：添加重复值的提示
          toast.warning('不允许添加重复值');
        }
      }
    };

    // 删除多输入框中的项
    const removeMultiInputItem = (param: Parameter, index: number) => {
      const currentValues = values[param.name] || [];
      const newValues = [...currentValues];
      newValues.splice(index, 1);
      handleValueChange(param.name, newValues);
    };

    const parseDateString = (
      dateStr: string,
      format: string
    ): Date | undefined => {
      if (!dateStr) return undefined;

      try {
        let parsedDate: dayjs.Dayjs;

        if (format === 'YYYYMMDD') {
          // 处理 YYYYMMDD 格式
          if (!/^\d{8}$/.test(dateStr)) {
            return undefined;
          }
          parsedDate = dayjs(dateStr, 'YYYYMMDD');
        } else {
          // 默认处理 YYYY-MM-DD 格式
          if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
            return undefined;
          }
          parsedDate = dayjs(dateStr, 'YYYY-MM-DD');
        }

        return parsedDate.isValid() ? parsedDate.toDate() : undefined;
      } catch {
        return undefined;
      }
    };

    const renderParameterInput = (param: Parameter) => {
      const inputComponent = (() => {
        switch (param.config.type) {
          case 'single_select':
            return (
              <Combobox
                options={
                  nameToChoices[param.name]?.map((choice) => ({
                    key: choice.value,
                    value: choice.value,
                  })) || []
                }
                value={values[param.name] || []}
                placeholder='请选择'
                onValueChange={(value) =>
                  handleValueChange(param.name, value as string[])
                }
                mode='single'
              />
            );

          case 'multi_select':
            return (
              <Combobox
                options={
                  nameToChoices[param.name]?.map((choice) => ({
                    key: choice.value,
                    value: choice.value,
                  })) || []
                }
                value={values[param.name] || []}
                placeholder='请选择'
                onValueChange={(value) =>
                  handleValueChange(param.name, value as string[])
                }
                mode='multiple'
              />
            );

          case 'date_picker':
            return (
              <DatePicker
                date={
                  values[param.name]
                    ? parseDateString(
                        values[param.name],
                        (param.config as DatePickerParamConfig).dateFormat
                      )
                    : undefined
                }
                setDate={(date) => {
                  if (date) {
                    let dateFormat = (param.config as DatePickerParamConfig)
                      .dateFormat;
                    dateFormat =
                      dateFormat === 'YYYYMMDD' ? 'YYYYMMDD' : 'YYYY-MM-DD';

                    // 使用 dayjs 替换 toLocaleDateString
                    const dateString = dayjs(date).format(dateFormat);
                    handleValueChange(param.name, dateString);
                  } else {
                    handleValueChange(param.name, '');
                  }
                }}
                dateFormat={(param.config as DatePickerParamConfig).dateFormat}
              />
            );

          case 'date_range_picker':
            return (
              <DateRangePicker
                dateRange={
                  values[param.name] && Array.isArray(values[param.name])
                    ? values[param.name].map((date: string) =>
                        parseDateString(
                          date,
                          (param.config as DateRangePickerParamConfig)
                            .dateFormat
                        )
                      )
                    : [undefined, undefined]
                }
                setDateRange={(dateRange) => {
                  let dateFormat = (param.config as DateRangePickerParamConfig)
                    .dateFormat;
                  dateFormat =
                    dateFormat === 'YYYYMMDD' ? 'YYYYMMDD' : 'YYYY-MM-DD';

                  // 使用 dayjs 替换 toLocaleDateString
                  const dateString = dateRange.map((date) =>
                    date ? dayjs(date).format(dateFormat) : ''
                  );
                  handleValueChange(param.name, dateString);
                }}
                dateFormat={
                  (param.config as DateRangePickerParamConfig).dateFormat
                }
              />
            );

          case 'multi_input':
            return (
              <div className='space-y-2'>
                <Input
                  placeholder={`输入${param.name}（按回车添加）`}
                  onKeyDown={(e) => handleMultiInputKeyDown(e, param)}
                />
                <div className='flex flex-wrap gap-2 mb-2'>
                  {(values[param.name] || []).map(
                    (value: string, index: number) => (
                      <div
                        key={`${value}-${index}`}
                        className='flex items-center bg-muted rounded-md px-2 py-1 text-xs'
                      >
                        <span className='mr-2'>{value}</span>
                        <Button
                          variant='ghost'
                          size='icon'
                          className='h-4 w-4 hover:bg-destructive/20'
                          onClick={() => removeMultiInputItem(param, index)}
                        >
                          <X size={12} />
                        </Button>
                      </div>
                    )
                  )}
                </div>
              </div>
            );

          case 'single_input':
          default:
            return (
              <Input
                defaultValue={values[param.name] || ''}
                onChange={(e) => handleValueChange(param.name, e.target.value)}
              />
            );
        }
      })();

      return (
        <div className='space-y-2'>
          <div className='flex items-center gap-1'>
            {param.description ? (
              <TooltipProvider delayDuration={1000}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Label htmlFor={param.name}>
                      {param.alias
                        ? `${param.alias}(${param.name})`
                        : param.name}
                    </Label>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>{param.description}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            ) : (
              <Label htmlFor={param.name}>
                <div>
                  {param.alias ? `${param.alias}(${param.name})` : param.name}
                </div>
              </Label>
            )}
          </div>
          {inputComponent}
        </div>
      );
    };

    console.info('渲染了的啊', queryStatus);
    return (
      <Card className='w-full'>
        <CardContent>
          <form onSubmit={handleSubmit} id={`form-${activeTabId}`}>
            <Tabs
              defaultValue='parameters'
              value={activeParameterTab}
              onValueChange={(value) => setActiveParameterTab(value)}
            >
              {/* tabs */}
              <div className='flex justify-between items-center mb-2 '>
                <div className='flex items-center'>
                  <TabsList>
                    <TabsTrigger
                      value='parameters'
                      className='flex items-center gap-1'
                    >
                      <Search size={14} />
                      查询参数 ({parameters?.length})
                    </TabsTrigger>
                    {requireFileUpload && (
                      <TabsTrigger
                        value='upload'
                        className='flex items-center gap-1'
                      >
                        <Upload size={14} />
                        <span>文件上传 ({csvDataSources.length})</span>
                      </TabsTrigger>
                    )}
                  </TabsList>
                  <div className='flex space-x-2 ml-4'>
                    {dataSources?.map((source) => (
                      <button
                        key={source.id}
                        type='button'
                        onClick={() => {
                          const currentQueryStatus = queryStatus[source.id];
                          if (source && currentQueryStatus) {
                            openDataSourceDialog(source, currentQueryStatus);
                          }
                        }}
                        className={`w-3 h-3 rounded-full  shadow-sm   cursor-pointer ${
                          queryStatus?.[source.id]
                            ? queryStatusColor(queryStatus[source.id].status)
                            : 'bg-gray-300 hover:bg-gray-400'
                        }`}
                      />
                    ))}
                  </div>
                </div>
                <div className='flex items-center space-x-2'>
                  <Button
                    type='submit'
                    size='sm'
                    className='h-8 w-15 px-2'
                    disabled={isQuerying}
                  >
                    查询
                  </Button>
                  <Button
                    variant='outline'
                    size='sm'
                    className='h-8 w-15 px-2'
                    onClick={onEditReport}
                    type='button'
                  >
                    编辑
                  </Button>

                  <Button
                    variant='ghost'
                    size='sm'
                    onClick={toggleParametersExpanded}
                    className='border-1'
                    type='button'
                  >
                    {parametersExpanded ? (
                      <ChevronUp size={16} className='text-muted-foreground' />
                    ) : (
                      <ChevronDown
                        size={16}
                        className='text-muted-foreground'
                      />
                    )}
                  </Button>
                </div>
              </div>

              {/* 参数 */}
              {parametersExpanded &&
                values &&
                Object.keys(values).length > 0 && (
                  <TabsContent value='parameters' className='mt-2 space-y-4'>
                    <div className='grid grid-cols-2 md:grid-cols-4 gap-x-10 gap-y-3'>
                      {parameters?.map((param) => (
                        <div key={param.name} className='col-span-1'>
                          {renderParameterInput(param)}
                        </div>
                      ))}
                    </div>
                  </TabsContent>
                )}

              {parametersExpanded && requireFileUpload && (
                <TabsContent value='upload' className='mt-2'>
                  <FileUploadArea
                    dataSources={csvDataSources}
                    files={files}
                    setFiles={setFiles}
                  />
                </TabsContent>
              )}
            </Tabs>
          </form>
        </CardContent>
      </Card>
    );
  }
);

export const queryStatusColor = (status: DataSourceStatus) => {
  // 暂时的想法是： 成功或未初始化，都为白色
  switch (status) {
    case DataSourceStatus.SUCCESS:
      return 'bg-green-300 hover:bg-green-500 opacity-60 hover:opacity-100';
    // return '';
    case DataSourceStatus.ERROR:
      return 'bg-red-500 hover:bg-red-600';
    case DataSourceStatus.RUNNING:
      return 'bg-blue-500 hover:bg-blue-600  opacity-60 hover:opacity-100';
    default:
      return 'bg-gray-300 hover:bg-gray-400  opacity-60 hover:opacity-100';
    // return '';
  }
};
