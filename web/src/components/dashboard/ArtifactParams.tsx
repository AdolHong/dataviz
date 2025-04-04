import { type Artifact } from '@/types/models/artifact';
import { Badge } from '@/components/ui/badge';
import { useState } from 'react';
import type { QueryStatus } from '@/lib/store/useTabQueryStatusStore';
import type { DataSource } from '@/types/models/dataSource';
import { CascaderTreeView } from './CascaderTreeView';
import type { TreeViewItem } from '@/components/tree-view';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

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

  // 级联参数树形视图中选择变化的处理
  const handleTreeViewCheckChange = (
    dfAlias: string,
    level: string,
    item: TreeViewItem,
    checked: boolean
  ) => {
    const paramKey = `${dfAlias}_${level}`;

    setParamValues((prev) => {
      const currentValues = Array.isArray(prev[paramKey])
        ? [...(prev[paramKey] as string[])]
        : [];

      // 如果选中，添加值；如果取消选中，移除值
      if (checked) {
        if (!currentValues.includes(item.name)) {
          return {
            ...prev,
            [paramKey]: [...currentValues, item.name],
          };
        }
      } else {
        return {
          ...prev,
          [paramKey]: currentValues.filter((val) => val !== item.name),
        };
      }

      return prev;
    });
  };

  return (
    <div className='border-l border-gray-200 pl-3 w-[250px] my-5 flex flex-col h-full'>
      <h3 className='text-sm font-medium mb-3 flex-shrink-0'>参数列表</h3>

      {/* 级联参数 */}
      {artifact.cascaderParams && artifact.cascaderParams.length > 0 && (
        <div>
          <div className='space-y-2'>
            {artifact.cascaderParams.map((param, index) => (
              <div key={index} className='bg-gray-50 p-2 rounded-md'>
                <div className='flex items-center mb-1 justify-between'>
                  <div className='flex items-center'>
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
                </div>

                {/* 仅显示树形视图 */}
                <div className='mt-2'>
                  <CascaderTreeView
                    dfAlias={param.dfAlias}
                    cascaderParam={param}
                    dataSources={dataSources}
                    dependentQueryStatus={dependentQueryStatus}
                    onCheckChange={(item, checked) => {
                      // 如果有levels，使用第一个level作为默认
                      if (param.levels && param.levels.length > 0) {
                        handleTreeViewCheckChange(
                          param.dfAlias,
                          param.levels[0].dfColumn,
                          item,
                          checked
                        );
                      }
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
