import { type Artifact } from '@/types/models/artifact';
import { Badge } from '@/components/ui/badge';
import type { QueryStatus } from '@/lib/store/useQueryStatusStore';
import type { DataSource } from '@/types/models/dataSource';
import { CascaderTreeView } from './CascaderTreeView';

import { Combobox } from '@/components/combobox';

import type { TreeNodeData } from '../tree-select/types';
import { getChildrenValuesByTargetValues } from './CascaderTreeView';
interface LayoutItemParamsProps {
  artifact: Artifact;
  dependentQueryStatus: Record<string, QueryStatus>;
  dataSources: DataSource[];
  plainParamValues: Record<string, string | string[]>;
  setPlainParamValues: (values: Record<string, string | string[]>) => void;
  cascaderParamValues: Record<string, string | string[]>;
  setCascaderParamValues: (values: Record<string, string | string[]>) => void;
  plainParamChoices: Record<string, Record<string, string>[]>;
  setPlainParamChoices: (
    values: Record<string, Record<string, string>[]>
  ) => void;
}

export function LayoutItemParams({
  artifact,
  dependentQueryStatus,
  dataSources,
  plainParamValues,
  cascaderParamValues,
  setPlainParamValues,
  setCascaderParamValues,
  plainParamChoices,
}: LayoutItemParamsProps) {
  if (!artifact) return null;

  // 修改后的代码
  const handleValueChange = (paramName: string, value: string | string[]) => {
    setPlainParamValues((prev) => {
      // 如果值没有变化，不更新状态
      if (JSON.stringify(prev[paramName]) === JSON.stringify(value)) {
        return prev;
      }
      return {
        ...prev,
        [paramName]: value,
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
    setCascaderParamValues((prev) => {
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
                    value={plainParamValues?.[param.name] || []}
                    placeholder='请选择'
                    onValueChange={(value) =>
                      handleValueChange(param.name, value)
                    }
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
