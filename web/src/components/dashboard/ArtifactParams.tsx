import { type Artifact } from '@/types/models/artifact';
import { Badge } from '@/components/ui/badge';
import { useState } from 'react';
import { Combobox } from '@/components/combobox';
import type { QueryStatus } from '@/lib/store/useTabQueryStatusStore';

interface ArtifactParamsProps {
  artifact: Artifact;
  dependentQueryStatus: Record<string, QueryStatus>;
}

export function ArtifactParams({
  artifact,
  dependentQueryStatus,
}: ArtifactParamsProps) {
  if (!artifact) return null;

  // 为每个参数创建状态
  const [paramValues, setParamValues] = useState<
    Record<string, string | string[]>
  >({});

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

  return (
    <div className='border-l border-gray-200 pl-3 w-[250px] my-5 flex flex-col h-full'>
      <h3 className='text-sm font-medium mb-3 flex-shrink-0'>参数列表</h3>

      {/* 参数列表 */}
      <div className='space-y-3 overflow-auto flex-grow pr-2'>
        {/* 级联参数 */}
        {artifact.cascaderParams && artifact.cascaderParams.length > 0 && (
          <div>
            <div className='space-y-2'>
              {artifact.cascaderParams.map((param, index) => (
                <div key={index} className='bg-gray-50 p-2 rounded-md'>
                  <div className='flex items-center mb-1'>
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
                  {param.levels && param.levels.length > 0 && (
                    <div className='space-y-2'>
                      {param.levels.map((level, i) => {
                        const paramKey = `${param.dfAlias}_${level.dfColumn}`;
                        return (
                          <div key={i} className='mt-1'>
                            <div className='text-[10px] mb-1 truncate'>
                              <span className='text-gray-600'>
                                {level.name || level.dfColumn}
                              </span>
                            </div>
                            <Combobox
                              options={[]}
                              value={paramValues[paramKey] || []}
                              placeholder='请选择'
                              onValueChange={(value) =>
                                handleValueChange(paramKey, value)
                              }
                              mode='multiple'
                            />
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              ))}
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
                    options={param.choices.map((choice) => ({
                      key: choice,
                      value: choice,
                    }))}
                    value={
                      paramValues[param.name] ||
                      (param.type === 'single'
                        ? param.default
                        : Array.isArray(param.default)
                          ? param.default
                          : [param.default])
                    }
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
