import { type Artifact } from '@/types/models/artifact';
import { Badge } from '@/components/ui/badge';
import type { QueryStatus } from '@/lib/store/useQueryStatusStore';
import type { DataSource } from '@/types/models/dataSource';
import { CascaderTreeView } from './CascaderTreeView';

import { Combobox } from '@/components/combobox';

import type { TreeNodeData } from '../tree-select/types';
import { getChildrenValuesByTargetValues } from './CascaderTreeView';
import type { PlainParamValue } from '@/types/api/aritifactRequest';
import type { SingleInferredParam, MultipleInferredParam } from '@/types';

interface LayoutItemParamsProps {
  artifact: Artifact;
  dependentQueryStatus: Record<string, QueryStatus>;
  dataSources: DataSource[];
  plainParamValues: Record<string, PlainParamValue>;
  setPlainParamValues: (
    values:
      | Record<string, PlainParamValue>
      | ((
          prev: Record<string, PlainParamValue>
        ) => Record<string, PlainParamValue>)
  ) => void;
  setCascaderParamValues: (
    values:
      | Record<string, string | string[]>
      | ((
          prev: Record<string, string | string[]>
        ) => Record<string, string | string[]>)
  ) => void;
  plainParamChoices: Record<string, Record<string, string>[]>;
  setPlainParamChoices: (
    values: Record<string, Record<string, string>[]>
  ) => void;
  // 新增参数，用于获取推断参数的选项
  inferredParamChoices?: Record<string, Record<string, string>[]>;
  inferredParamValues?: Record<string, string | string[]>;
  setInferredParamValues?: (
    values:
      | Record<string, string | string[]>
      | ((
          prev: Record<string, string | string[]>
        ) => Record<string, string | string[]>)
  ) => void;
}

export function LayoutItemParams({
  artifact,
  dependentQueryStatus,
  dataSources,
  plainParamValues,
  setPlainParamValues,
  setCascaderParamValues,
  plainParamChoices,
  inferredParamChoices = {},
  inferredParamValues = {},
  setInferredParamValues = () => {},
}: LayoutItemParamsProps) {
  if (!artifact) return null;

  // 修改后的代码
  const handleValueChange = (
    paramName: string,
    value: string | string[],
    valueType: 'string' | 'double' | 'boolean' | 'int',
    type: 'single' | 'multiple'
  ) => {
    setPlainParamValues((prev: Record<string, PlainParamValue>) => {
      // 如果值没有变化，不更新状态
      if (JSON.stringify(prev[paramName]) === JSON.stringify(value)) {
        return prev;
      }
      return {
        ...prev,
        [paramName]: {
          name: paramName,
          type: type,
          valueType: valueType,
          value: value,
        },
      };
    });
  };

  // 处理推断参数值变化
  const handleInferredValueChange = (
    paramId: string,
    value: string | string[]
  ) => {
    setInferredParamValues((prev) => {
      // 如果值没有变化，不更新状态
      if (JSON.stringify(prev[paramId]) === JSON.stringify(value)) {
        return prev;
      }
      return {
        ...prev,
        [paramId]: value,
      };
    });
  };

  // 级联参数树形视图中选择变化的处理
  const handleTreeViewCheckChange = (
    dfAlias: string,
    itemLevel: string,
    selectedValues: string[],
    treeData: TreeNodeData[]
  ) => {
    const paramKey = `${dfAlias},${itemLevel}`;
    // 根据节点类型和选择状态更新参数值
    setCascaderParamValues((prev: Record<string, string | string[]>) => {
      const currentValues = getChildrenValuesByTargetValues(
        treeData,
        selectedValues
      );
      // 返回更新后的状态
      return {
        ...prev,
        [paramKey]: currentValues,
      };
    });
  };

  // 获取推断参数的标识，用于在UI中显示和获取值
  const getInferredParamKey = (
    param: SingleInferredParam | MultipleInferredParam
  ) => {
    return `${param.dfAlias}_${param.dfColumn}_${param.id}`;
  };

  return (
    <div className='border-l border-gray-200 pl-3 w-[250px] my-5 flex flex-col h-full'>
      <h3 className='text-sm font-medium mb-3 flex-shrink-0'>参数列表</h3>

      {/* 参数列表 */}
      <div className='space-y-3 overflow-auto flex-grow pr-2'>
        {/* 级联参数 */}
        {artifact.cascaderParams && artifact.cascaderParams.length > 0 && (
          <div className='space-y-4'>
            {artifact.cascaderParams.map((param, index) => {
              return (
                <div key={index} className='bg-gray-50 p-3 rounded-md'>
                  <div className='flex items-center mb-2'>
                    <Badge
                      variant='outline'
                      className='mr-1.5 bg-green-50 text-green-700 border-green-200 text-[10px] px-1.5 py-0'
                    >
                      级联
                    </Badge>
                    <span className='text-xs font-medium truncate mr-5'>
                      {param.dfAlias}
                    </span>
                    <div className='flex flex-row gap-1'>
                      {param.levels &&
                        param.levels.map((level, i) => (
                          <span key={i} className='text-[10px]'>
                            ({level.name || level.dfColumn})
                            {i < param.levels.length - 1 ? ', ' : ''}
                          </span>
                        ))}
                    </div>
                  </div>

                  <div className='mt-1' key={`cascader-${index}`}>
                    <CascaderTreeView
                      dfAlias={param.dfAlias}
                      cascaderParam={param}
                      dataSources={dataSources}
                      dependentQueryStatus={dependentQueryStatus}
                      onCheckChange={(selectedValues, treeData) => {
                        if (param.levels && param.levels.length > 0) {
                          handleTreeViewCheckChange(
                            param.dfAlias,
                            param.levels[param.levels.length - 1].dfColumn,
                            selectedValues,
                            treeData
                          );
                        }
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* 单列推断参数 */}
        {artifact?.inferredParams && artifact.inferredParams.length > 0 && (
          <div className='mb-3'>
            <div className='space-y-2'>
              {artifact.inferredParams.map((param) => {
                const paramKey = getInferredParamKey(param);
                return (
                  <div key={param.id} className='bg-gray-50 p-2 rounded-md'>
                    <div className='flex items-center mb-1'>
                      <Badge
                        variant='outline'
                        className='mr-1.5 bg-purple-50 text-purple-700 border-purple-200 text-[10px] px-1.5 py-0'
                      >
                        {param.type === 'single' ? '单列单选' : '单列多选'}
                      </Badge>
                      <span className='text-xs font-medium truncate'>
                        {param.alias || `${param.dfAlias}.${param.dfColumn}`}
                      </span>
                    </div>
                    {param.description && (
                      <div className='text-[10px] text-gray-500 mb-1.5 line-clamp-1'>
                        {param.description}
                      </div>
                    )}

                    <Combobox
                      options={
                        inferredParamChoices[paramKey]?.map((choice) => ({
                          key: choice.key,
                          value: choice.value,
                        })) || []
                      }
                      value={
                        inferredParamValues[paramKey] ||
                        (param.type === 'single' ? '' : [])
                      }
                      placeholder='请选择'
                      onValueChange={(value) =>
                        handleInferredValueChange(paramKey, value)
                      }
                      clearAble={param.clearable}
                      mode={param.type === 'single' ? 'single' : 'multiple'}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 普通参数 */}
        {artifact.plainParams && artifact.plainParams.length > 0 && (
          <div className='mb-3'>
            {/* <h4 className='text-xs font-medium text-gray-500 mb-2'>基础参数</h4> */}
            <div className='space-y-2'>
              {artifact.plainParams.map((param) => (
                <div key={param.id} className='bg-gray-50 p-2 rounded-md'>
                  <div className='flex items-center mb-1'>
                    <Badge
                      variant='outline'
                      className='mr-1.5 bg-blue-50 text-blue-700 border-blue-200 text-[10px] px-1.5 py-0'
                    >
                      {param.type === 'single' ? '单选' : '多选'}
                    </Badge>
                    <span className='text-xs font-medium truncate'>
                      {param.alias || param.name}
                    </span>
                  </div>
                  {param.description && (
                    <div className='text-[10px] text-gray-500 mb-1.5 line-clamp-1'>
                      {param.description}
                    </div>
                  )}

                  {/* 使用Combobox进行选择 */}
                  <Combobox
                    options={
                      plainParamChoices[param.name]?.map((choice) => ({
                        key: choice.key,
                        value: choice.value,
                      })) || []
                    }
                    value={plainParamValues?.[param.name]?.value || []}
                    placeholder='请选择'
                    onValueChange={(value) =>
                      handleValueChange(
                        param.name,
                        value,
                        param.valueType,
                        param.type
                      )
                    }
                    clearAble={param.type === 'single' ? false : true}
                    mode={param.type === 'single' ? 'single' : 'multiple'}
                  />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
