// web/src/components/dashboard/AntdCascaderView.tsx
import { useMemo, useState } from 'react';
import { Cascader } from 'antd';
import Papa from 'papaparse';
import type { DataSource } from '@/types/models/dataSource';
import type { QueryStatus } from '@/lib/store/useQueryStatusStore';
import type { CascaderParam } from '@/types/models/artifact';

// 定义级联选项的类型
interface CascaderOption {
  value: string;
  label: string;
  children?: CascaderOption[];
}

function csvToCascaderOptions(
  csvData: string,
  levels: string[]
): CascaderOption[] {
  const { data } = Papa.parse(csvData, {
    header: true,
    skipEmptyLines: true,
  });

  const result: CascaderOption[] = [];
  const levelMap = new Map<string, CascaderOption>();

  data.forEach((row: any) => {
    let parentOption: CascaderOption | undefined = undefined;

    levels.forEach((level, index) => {
      const value = row[level];
      const mapKey = levels
        .slice(0, index + 1)
        .map((l) => row[l])
        .join('__');

      if (!levelMap.has(mapKey)) {
        const newOption: CascaderOption = {
          value: value.replace(/\s+/g, '-'),
          label: value,
          children: index < levels.length - 1 ? [] : undefined,
        };

        if (parentOption && parentOption.children) {
          parentOption.children.push(newOption);
        } else if (index === 0) {
          result.push(newOption);
        }

        levelMap.set(mapKey, newOption);
        parentOption = newOption;
      } else {
        parentOption = levelMap.get(mapKey);
      }
    });
  });

  return result;
}

// 针对单选列表，递归获取第一个选项的值
function extractCascaderFirstLevelValues(options: CascaderOption[]): string[] {
  const values: string[] = [];

  function traverse(option: CascaderOption) {
    values.push(option.value);

    if (option.children && option.children.length > 0) {
      traverse(option.children[0]);
    }
  }

  if (options.length > 0) {
    traverse(options[0]);
  }

  return values;
}

interface AntdCascaderViewProps {
  dfAlias: string;
  dataSources: DataSource[];
  cascaderParam: CascaderParam;
  dependentQueryStatus: Record<string, QueryStatus>;
  onCheckChange?: (selectedValues: string[] | string[][]) => void;
  multiple?: boolean;
}

export function AntdCascaderView({
  dfAlias,
  dataSources,
  cascaderParam,
  dependentQueryStatus,
  onCheckChange,
  multiple = false,
}: AntdCascaderViewProps) {
  const [value, setValue] = useState<string[][] | string[]>([]);

  // 找到对应的数据源
  const dataSource = useMemo(() => {
    return dataSources.find((ds) => ds.alias === dfAlias);
  }, [dataSources, dfAlias]);

  // 获取级联层级
  const levels = useMemo(() => {
    if (!dataSource) return [];

    const queryStatus = dependentQueryStatus[dataSource.id];
    if (!queryStatus?.queryResponse?.cascaderContext?.inferred) return [];

    return cascaderParam.levels.map((level) => level.dfColumn);
  }, [dataSource, dependentQueryStatus, cascaderParam]);

  // 获取CSV数据
  const csvData = useMemo(() => {
    if (!dataSource) return null;

    const queryStatus = dependentQueryStatus[dataSource.id];
    if (!queryStatus?.queryResponse?.cascaderContext?.inferred) return null;

    const cascaderTuple = cascaderParam.levels.map((level) => level.dfColumn);
    const cascaderKey = JSON.stringify(cascaderTuple);

    // 设置value初始化
    setValue([]);

    return queryStatus.queryResponse.cascaderContext.inferred[
      cascaderKey
    ] as string;
  }, [dataSource, dependentQueryStatus, cascaderParam]);

  // 将CSV数据转换为Cascader选项
  const options = useMemo(() => {
    if (!csvData) return [];
    const options = csvToCascaderOptions(csvData, levels);

    // 如果非多选，且有数据，则设置value为第一个选项
    if (!cascaderParam.multiple && options.length > 0) {
      // 延迟0.1秒后渲染，以确保数据正确加载
      setTimeout(() => {
        const firstLevelValues = extractCascaderFirstLevelValues(options);
        setValue(firstLevelValues);
        onCheckChange?.([firstLevelValues as string[]]); // 触发onCheckChange, 更新cascaderParamValues
      }, 100);
    }

    return options;
  }, [csvData, levels]);

  // 渲染处理
  if (!dataSource) {
    return (
      <Cascader
        style={{ width: '100%' }}
        options={[]}
        disabled
        placeholder='找不到数据源'
      />
    );
  }

  if (!csvData) {
    return (
      <Cascader
        style={{ width: '100%' }}
        options={[]}
        disabled
        placeholder='无级联数据可用'
      />
    );
  }

  if (multiple) {
    return (
      <Cascader
        options={options}
        value={value as string[][]}
        multiple={true}
        maxTagCount='responsive'
        placeholder='请选择'
        onChange={(value) => {
          setValue(value as string[][]);
          if (onCheckChange) {
            onCheckChange(value as string[][]);
          }
        }}
        allowClear={true}
        style={{ width: '100%' }}
      />
    );
  }

  return (
    <Cascader
      style={{ width: '100%' }}
      value={value as string[]}
      options={options}
      onChange={(value) => {
        setValue([value as string[]]);
        if (onCheckChange) {
          onCheckChange([value as string[]]);
        }
      }}
      placeholder='请选择'
      allowClear={false}
    />
  );
}
