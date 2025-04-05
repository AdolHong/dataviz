import { useMemo, useState } from 'react';
import type { DataSource } from '@/types/models/dataSource';
import type { QueryStatus } from '@/lib/store/useQueryStatusStore';
import Papa from 'papaparse';
import type { CascaderParam } from '@/types/models/artifact';
import { Button } from '@/components/ui/button';
import { TreeSelect } from '../tree-select/tree-select';

interface TreeNodeData {
  name: string;
  value: string;
  children?: TreeNodeData[];
}

function csvToTreeData(csvData: string, levels: string[]): TreeNodeData[] {
  // 使用Papa Parse解析CSV
  const { data } = Papa.parse(csvData, {
    header: true,
    skipEmptyLines: true,
  });

  // 存储结果的树形结构
  const result: TreeNodeData[] = [];

  // 遍历CSV的每一行
  data.forEach((row: any) => {
    // 从根节点开始处理
    let currentLevel = result;
    let parentNode: TreeNodeData | null = null;

    // 遍历每一层级
    for (let i = 0; i < levels.length; i++) {
      const level = levels[i];
      const value = row[level];

      // 查找当前值是否已存在于当前层级中
      let node = currentLevel.find((node) => node.name === value);

      // 如果不存在，创建新节点
      if (!node) {
        node = {
          name: value,
          value: value.toLowerCase().replace(/\s+/g, '-'), // 根据名称生成value值
        };

        // 如果不是最后一层，添加children数组
        if (i < levels.length - 1) {
          node.children = [];
        }

        // 将新节点添加到当前层级
        currentLevel.push(node);
      }

      // 如果不是最后一层，移动到下一层级
      if (i < levels.length - 1) {
        if (!node.children) {
          node.children = [];
        }
        currentLevel = node.children;
      }
    }
  });

  return result;
}

export function getChildrenValuesByTargetValues(
  treeData: TreeNodeData[],
  targetValues: string[]
): string[] {
  const result: string[] = [];

  // 递归函数，用于遍历树结构
  function traverse(nodes: TreeNodeData[]) {
    for (const node of nodes) {
      // 如果当前节点的value在目标值列表中
      if (targetValues.includes(node.value)) {
        // 如果是叶子节点，则添加自身
        if (!node.children || node.children.length === 0) {
          result.push(node.value);
        }
        // 如果有子节点，则添加所有子节点的值
        else {
          collectAllChildrenValues(node, result);
        }
      }
      // 继续遍历子节点
      else if (node.children && node.children.length > 0) {
        traverse(node.children);
      }
    }
  }

  // 收集所有子节点的值
  function collectAllChildrenValues(node: TreeNodeData, values: string[]) {
    if (!node.children || node.children.length === 0) {
      values.push(node.value);
      return;
    }

    for (const child of node.children) {
      collectAllChildrenValues(child, values);
    }
  }

  traverse(treeData);
  return result;
}

interface CascaderTreeViewProps {
  dfAlias: string;
  dataSources: DataSource[];
  cascaderParam: CascaderParam;
  dependentQueryStatus: Record<string, QueryStatus>;
  onCheckChange?: (selectedValues: string[], treeData: TreeNodeData[]) => void;
}

export function CascaderTreeView({
  dfAlias,
  dataSources,
  cascaderParam,
  dependentQueryStatus,
  onCheckChange,
}: CascaderTreeViewProps) {
  // 1. 根据dfAlias找到对应的dataSource和sourceId
  const dataSource = useMemo(() => {
    return dataSources.find((ds) => ds.alias === dfAlias);
  }, [dataSources, dfAlias]);

  const levels = useMemo(() => {
    if (!dataSource) return [];

    const queryStatus = dependentQueryStatus[dataSource.id];
    if (!queryStatus?.queryResponse?.cascaderContext?.inferred) return [];

    let cascaderTuple: string[] = [];
    cascaderParam.levels.forEach((level) => {
      cascaderTuple.push(level.dfColumn);
    });
    return cascaderTuple;
  }, [dataSource, dependentQueryStatus, cascaderParam]);

  // 2. 从dependentQueryStatus找到对应的cascaderContext数据
  const csvData = useMemo(() => {
    if (!dataSource) return null;

    const queryStatus = dependentQueryStatus[dataSource.id];
    if (!queryStatus?.queryResponse?.cascaderContext?.inferred) return null;

    let cascaderTuple: string[] = [];
    cascaderParam.levels.forEach((level) => {
      cascaderTuple.push(level.dfColumn);
    });
    const cascaderKey = JSON.stringify(cascaderTuple);

    const inferredCsvData = queryStatus.queryResponse.cascaderContext.inferred[
      cascaderKey
    ] as string;

    return inferredCsvData;
  }, [dataSource, dependentQueryStatus, cascaderParam]);

  // 3. 将CSV数据转换为TreeView格式
  const treeData = useMemo(() => {
    if (!csvData) return [];

    const treeData = csvToTreeData(csvData, levels);
    return treeData;
  }, [csvData]);

  if (!dataSource) {
    return (
      <Button
        variant='outline'
        className='w-full justify-between text-left font-normal text-xs'
        disabled
      >
        找不到数据源
      </Button>
    );
  }

  if (!csvData) {
    return (
      <Button
        variant='outline'
        className='w-full justify-between text-left font-normal text-xs'
        disabled
      >
        无级联数据可用
      </Button>
    );
  }

  const [value, setValue] = useState<string[]>([]);
  console.info('value', value);

  return (
    <TreeSelect
      className='w-full'
      data={treeData}
      value={value}
      onValueChange={(v: string[]) => {
        setValue(v);
        if (onCheckChange) {
          onCheckChange(v, treeData);
        }
      }}
    />
  );
}
