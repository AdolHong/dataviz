// web/src/components/dashboard/AntdCascaderView.tsx
import { useMemo, useState } from 'react';
import { Cascader } from 'antd';
import type { CascaderProps } from 'antd/es/cascader';
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
          value: value.toLowerCase().replace(/\s+/g, '-'),
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

interface AntdCascaderViewProps {
  dfAlias: string;
  dataSources: DataSource[];
  cascaderParam: CascaderParam;
  dependentQueryStatus: Record<string, QueryStatus>;
  onCheckChange?: (selectedValues: string[], options: CascaderOption[]) => void;
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
  const [value, setValue] = useState<string[]>([]);

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

    return queryStatus.queryResponse.cascaderContext.inferred[
      cascaderKey
    ] as string;
  }, [dataSource, dependentQueryStatus, cascaderParam]);

  // 将CSV数据转换为Cascader选项
  const options = useMemo(() => {
    if (!csvData) return [];
    return csvToCascaderOptions(csvData, levels);
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

  // Cascader 配置
  const cascaderProps: CascaderProps = {
    options,
    style: { width: '100%' },
    multiple,
    onChange: (value, selectedOptions) => {
      setValue(value as string[]);
      if (onCheckChange) {
        // 将选中的值和选项传递出去
        onCheckChange(value as string[], selectedOptions as CascaderOption[]);
      }
    },
    placeholder: '请选择',
    maxTagCount: 'responsive',
  };

  return <Cascader {...cascaderProps} />;
}
