import { type Artifact } from '@/types/models/artifact';
import { Badge } from '@/components/ui/badge';
import { useState, useEffect } from 'react';
import type { QueryStatus } from '@/lib/store/useTabQueryStatusStore';
import type { DataSource } from '@/types/models/dataSource';
import { CascaderTreeView } from './CascaderTreeView';
import type { TreeViewItem } from '@/components/tree-view';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Combobox } from '@/components/combobox';
import { parseDynamicDate } from '@/utils/parser';

interface ArtifactParamsProps {
  artifact: Artifact;
  dependentQueryStatus: Record<string, QueryStatus>;
  dataSources: DataSource[];
}

export function ArtifactParams({
  artifact,
  dependentQueryStatus,
  dataSources,
}: ArtifactParamsProps) {
  if (!artifact) return null;

  // 为每个参数创建状态
  const [paramValues, setParamValues] = useState<
    Record<string, string | string[]>
  >({});

  const [plainParamChoices, setPlainParamChoices] = useState<
    Record<string, Record<string, string>[]>
  >({});

  useEffect(() => {
    console.info('hi, paramValues', paramValues);

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
        setParamValues((prev) => ({
          ...prev,
          [param.name]: defaulVal,
        }));
      } else if (param.type === 'multiple') {
        const defaulVal = param.default.map((val) => parseDynamicDate(val));
        setParamValues((prev) => ({
          ...prev,
          [param.name]: defaulVal,
        }));
      }
    });
  }, [dependentQueryStatus]);

  // 修改后的代码
  const handleValueChange = (paramName: string, value: string | string[]) => {
    setParamValues((prev) => {
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
    item: TreeViewItem,
    checked: boolean
  ) => {
    const paramKey = `cascader,${dfAlias},${itemLevel}`;

    console.info('hi, paramKey', paramKey);
    // 根据节点类型和选择状态更新参数值
    setParamValues((prev) => {
      // 获取当前的值列表
      const currentValues: string[] = [...(prev[paramKey] || [])];

      // 递归处理节点及其子节点
      const processNode = (node: TreeViewItem, isChecked: boolean) => {
        // 只处理叶子节点或最底层节点
        if (node.type === 'item') {
          if (isChecked) {
            // 如果选中且不在当前值列表中，添加它
            if (!currentValues.includes(node.name)) {
              currentValues.push(node.name);
            }
          } else {
            // 如果取消选中，从当前值列表中移除
            const index = currentValues.indexOf(node.name);
            if (index !== -1) {
              currentValues.splice(index, 1);
            }
          }
        }

        // 如果有子节点，递归处理
        if (node.children && node.children.length > 0) {
          node.children.forEach((child) => processNode(child, isChecked));
        }
      };

      // 处理当前节点
      processNode(item, checked);

      console.info('hi, currentValues', currentValues);

      // 返回更新后的状态
      return {
        ...prev,
        [paramKey]: currentValues,
      };
    });

    setTimeout(() => {
      console.info('hi, paramValues', paramValues);
    }, 1000);
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
              // 为每个级联参数计算参数键
              const firstLevelKey =
                param.levels && param.levels.length > 0
                  ? `${param.dfAlias}_${param.levels[0].dfColumn}`
                  : '';

              // 获取已选中的值列表
              const selectedItems =
                firstLevelKey && paramValues[firstLevelKey]
                  ? Array.isArray(paramValues[firstLevelKey])
                    ? (paramValues[firstLevelKey] as string[])
                    : [paramValues[firstLevelKey] as string]
                  : [];

              return (
                <div key={index} className='bg-gray-50 p-3 rounded-md'>
                  <div className='flex items-center mb-2'>
                    <Badge
                      variant='outline'
                      className='mr-1.5 bg-green-50 text-green-700 border-green-200 text-[10px] px-1.5 py-0'
                    >
                      级联
                    </Badge>
                    <span className='text-xs font-medium truncate'>
                      {param.dfAlias}
                    </span>
                  </div>

                  <div className='mt-1'>
                    {param.levels &&
                      param.levels.map((level, i) => (
                        <div key={i} className='mb-1 text-[10px] text-gray-600'>
                          {level.name || level.dfColumn}
                        </div>
                      ))}
                    <CascaderTreeView
                      dfAlias={param.dfAlias}
                      cascaderParam={param}
                      dataSources={dataSources}
                      dependentQueryStatus={dependentQueryStatus}
                      selectedItems={selectedItems}
                      onCheckChange={(item, checked) => {
                        if (param.levels && param.levels.length > 0) {
                          handleTreeViewCheckChange(
                            param.dfAlias,
                            param.levels[param.levels.length - 1].dfColumn,
                            item,
                            checked
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
                    value={paramValues[param.name] || []}
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
// <Combobox
// options={
//   nameToChoices[param.name]?.map((choice) => ({
//     key: choice.value,
//     value: choice.value,
//   })) || []
// }
// value={values[param.name] || []}
// placeholder='请选择'
// onValueChange={(value) =>
//   handleValueChange(param.name, value as string[])
// }
// mode='single'
// />
