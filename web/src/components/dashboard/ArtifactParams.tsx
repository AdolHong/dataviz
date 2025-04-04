import {
  type Artifact,
  type SinglePlainParam,
  type MultiplePlainParam,
  type CascaderParam,
} from '@/types/models/artifact';
import { Badge } from '@/components/ui/badge';
import { useState } from 'react';
import { Combobox } from '@/components/combobox';

interface ArtifactParamsProps {
  artifact: Artifact;
}

export function ArtifactParams({ artifact }: ArtifactParamsProps) {
  if (!artifact) return null;

  // 为每个参数创建状态
  const [paramValues, setParamValues] = useState<
    Record<string, string | string[]>
  >({});

  const handleValueChange = (paramName: string, value: string | string[]) => {
    setParamValues((prev) => ({
      ...prev,
      [paramName]: value,
    }));
  };

  return (
    <div className='border-l border-gray-200 pl-4 min-w-[200px] max-w-[300px] overflow-auto my-3 py-2'>
      <h3 className='text-sm font-medium mb-3'>参数列表</h3>

      {/* 普通参数 */}
      {artifact.plainParams && artifact.plainParams.length > 0 && (
        <div className='mb-4'>
          <h4 className='text-xs font-medium text-gray-500 mb-2'>基础参数</h4>
          <div className='space-y-3'>
            {artifact.plainParams.map((param) => (
              <div key={param.id} className='bg-gray-50 p-3 rounded-md'>
                <div className='flex items-center mb-2'>
                  <Badge
                    variant='outline'
                    className='mr-2 bg-blue-50 text-blue-700 border-blue-200'
                  >
                    {param.type === 'single' ? '单选' : '多选'}
                  </Badge>
                  <span className='text-sm font-medium'>
                    {param.alias || param.name}
                  </span>
                </div>
                {param.description && (
                  <div className='text-xs text-gray-500 mb-2'>
                    {param.description}
                  </div>
                )}
                <div className='text-xs mb-2'>
                  <span className='text-gray-600'>类型: </span>
                  <span>{param.valueType}</span>
                </div>

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

      {/* 级联参数 */}
      {artifact.cascaderParams && artifact.cascaderParams.length > 0 && (
        <div>
          <h4 className='text-xs font-medium text-gray-500 mb-2'>级联参数</h4>
          <div className='space-y-3'>
            {artifact.cascaderParams.map((param, index) => (
              <div key={index} className='bg-gray-50 p-3 rounded-md'>
                <div className='flex items-center mb-2'>
                  <Badge
                    variant='outline'
                    className='mr-2 bg-green-50 text-green-700 border-green-200'
                  >
                    级联
                  </Badge>
                  <span className='text-sm font-medium'>{param.dfAlias}</span>
                </div>
                {param.levels && param.levels.length > 0 && (
                  <div className='mt-2 pl-3 border-l-2 border-green-200'>
                    {param.levels.map((level, i) => (
                      <div key={i} className='text-xs mb-2'>
                        <span className='text-gray-600'>
                          {level.name || level.dfColumn}:{' '}
                        </span>
                        <span>{level.description || level.dfColumn}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
