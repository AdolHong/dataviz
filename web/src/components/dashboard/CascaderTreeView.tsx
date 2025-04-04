import React, { useMemo } from 'react';
import TreeView from '@/components/tree-view';
import type { TreeViewItem } from '@/components/tree-view';
import type { DataSource } from '@/types/models/dataSource';
import type { QueryStatus } from '@/lib/store/useTabQueryStatusStore';
import Papa from 'papaparse';
import type { CascaderParam } from '@/types/models/artifact';
interface CascaderTreeViewProps {
  dfAlias: string;
  dataSources: DataSource[];
  cascaderParam: CascaderParam;
  dependentQueryStatus: Record<string, QueryStatus>;
  onCheckChange?: (item: TreeViewItem, checked: boolean) => void;
}

interface CsvRow {
  [key: string]: string;
}

export function CascaderTreeView({
  dfAlias,
  dataSources,
  cascaderParam,
  dependentQueryStatus,
  onCheckChange,
}: CascaderTreeViewProps) {
  console.info('hi, CascaderTreeView');

  // 1. 根据dfAlias找到对应的dataSource和sourceId
  const dataSource = useMemo(() => {
    return dataSources.find((ds) => ds.alias === dfAlias);
  }, [dataSources, dfAlias]);

  // 2. 从dependentQueryStatus找到对应的cascaderContext数据
  const csvData = useMemo(() => {
    if (!dataSource) return null;

    console.info('hi, dependentQueryStatus', dependentQueryStatus);
    console.info('hi, dataSource.id', dataSource.id);
    console.info('hi, dataSources', dataSources);
    const queryStatus = dependentQueryStatus[dataSource.id];
    if (!queryStatus?.queryResponse?.cascaderContext?.inferred) return null;
    console.info('2');
    let cascaderTuple: string[] = [];
    cascaderParam.levels.forEach((level) => {
      cascaderTuple.push(level.dfColumn);
    });
    const cascaderKey = JSON.stringify(cascaderTuple);
    console.info('3');
    console.info(
      'hi, queryStatus.queryResponse.cascaderContext.inferred',
      queryStatus.queryResponse.cascaderContext.inferred
    );
    console.info('hi, cascaderKey', cascaderKey);
    const inferredCsvData = queryStatus.queryResponse.cascaderContext.inferred[
      cascaderKey
    ] as string;

    return inferredCsvData;
  }, [dataSource, dependentQueryStatus]);

  console.info('hi, cascaderParam', cascaderParam);
  console.info('hi, csvData', csvData);

  // 3. 将CSV数据转换为TreeView格式
  const treeData = useMemo(() => {
    if (!csvData) return [];

    // 使用PapaParse解析CSV
    const { data } = Papa.parse<CsvRow>(csvData, {
      header: true,
      skipEmptyLines: true,
    });

    if (!data || data.length === 0) return [];

    // 获取所有列名
    const columns = Object.keys(data[0]);
    if (columns.length === 0) return [];

    // 构建树形结构
    const root: TreeViewItem = {
      id: 'root',
      name: '全部',
      type: 'root',
      children: [],
    };

    // 用于跟踪节点，避免重复创建
    const nodeMap = new Map<string, TreeViewItem>();
    nodeMap.set('root', root);

    // 处理每一行数据
    data.forEach((row, rowIndex) => {
      let currentParent = root;

      // 处理每一列，作为层级
      columns.forEach((column, colIndex) => {
        const value = row[column];
        if (!value) return;

        // 构建层级路径作为唯一标识
        const path = columns
          .slice(0, colIndex + 1)
          .map((col) => row[col])
          .join('|');

        // 如果节点已存在，使用现有节点
        if (nodeMap.has(path)) {
          currentParent = nodeMap.get(path)!;
          return;
        }

        // 创建新节点
        const newNode: TreeViewItem = {
          id: `${path}_${rowIndex}_${colIndex}`,
          name: value,
          type: colIndex === columns.length - 1 ? 'item' : 'folder',
          children: [],
        };

        // 将新节点添加到父节点
        if (!currentParent.children) {
          currentParent.children = [];
        }

        // 检查是否已存在同名节点
        const existingNode = currentParent.children.find(
          (child) => child.name === value
        );
        if (existingNode) {
          currentParent = existingNode;
        } else {
          currentParent.children.push(newNode);
          nodeMap.set(path, newNode);
          currentParent = newNode;
        }
      });
    });

    // 移除只有一个子节点的中间节点，使树更简洁
    const simplifyTree = (node: TreeViewItem): TreeViewItem => {
      if (node.children) {
        node.children = node.children.map(simplifyTree);

        // 如果节点只有一个子节点且类型相同，合并它们
        if (node.children.length === 1 && node.type === node.children[0].type) {
          const child = node.children[0];
          return {
            ...child,
            name: `${node.name} / ${child.name}`,
          };
        }
      }
      return node;
    };

    return [simplifyTree(root)];
  }, [csvData]);

  if (!csvData || treeData.length === 0) {
    return (
      <div className='p-4 text-sm text-muted-foreground'>
        {!dataSource ? '找不到数据源' : '无级联数据可用'}
      </div>
    );
  }

  return (
    <div className='max-h-[400px] overflow-auto p-2'>
      <TreeView
        data={treeData}
        showCheckboxes={true}
        searchPlaceholder='搜索...'
        selectionText='已选择'
        checkboxLabels={{
          check: '全选',
          uncheck: '取消全选',
        }}
        onCheckChange={onCheckChange}
      />
    </div>
  );
}
