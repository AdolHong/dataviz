import React, { useMemo, useState } from 'react';
import TreeView from '@/components/tree-view';
import type { TreeViewItem } from '@/components/tree-view';
import type { DataSource } from '@/types/models/dataSource';
import type { QueryStatus } from '@/lib/store/useTabQueryStatusStore';
import Papa from 'papaparse';
import type { CascaderParam } from '@/types/models/artifact';
import { Button } from '@/components/ui/button';
import { ChevronDown } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';

interface CsvRow {
  [key: string]: string;
}

interface TreeNode {
  id: string;
  name: string;
  type: string;
  children?: TreeNode[];
}

function csvToHierarchicalData(
  csvRows: CsvRow[],
  levels: string[]
): TreeNode[] {
  // Create the root node
  const root: TreeNode = {
    id: '1',
    name: 'Root',
    type: 'root',
    children: [],
  };

  // Create maps to track existing nodes at each level
  const provinceMap: Record<string, TreeNode> = {};
  const cityMap: Record<string, Record<string, TreeNode>> = {};

  // Process each CSV row
  csvRows.forEach((row) => {
    const province = row[levels[0]]; // 'province'
    const city = row[levels[1]]; // 'city'

    if (!province) return; // Skip if no province value

    // Handle province level
    if (!provinceMap[province]) {
      const provinceId = `1.${Object.keys(provinceMap).length + 1}`;
      const provinceNode: TreeNode = {
        id: provinceId,
        name: province,
        type: levels[0], // 'province'
        children: [],
      };
      root.children!.push(provinceNode);
      provinceMap[province] = provinceNode;
    }

    // Handle city level
    if (city && provinceMap[province]) {
      if (!cityMap[province]) {
        cityMap[province] = {};
      }

      if (!cityMap[province][city]) {
        const provinceNode = provinceMap[province];
        const cityId = `${provinceNode.id}.${(provinceNode.children?.length || 0) + 1}`;
        const cityNode: TreeNode = {
          id: cityId,
          name: city,
          type: levels[1], // 'city'
          children: [],
        };
        provinceNode.children!.push(cityNode);
        cityMap[province][city] = cityNode;
      }
    }
  });

  return [root];
}

interface CascaderTreeViewProps {
  dfAlias: string;
  dataSources: DataSource[];
  cascaderParam: CascaderParam;
  dependentQueryStatus: Record<string, QueryStatus>;
  onCheckChange?: (item: TreeViewItem, checked: boolean) => void;
  selectedItems?: string[]; // 已选中的项目名称列表
}

export function CascaderTreeView({
  dfAlias,
  dataSources,
  cascaderParam,
  dependentQueryStatus,
  onCheckChange,
  selectedItems = [],
}: CascaderTreeViewProps) {
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [selectedCount, setSelectedCount] = useState(selectedItems.length);

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

    // 使用PapaParse解析CSV
    const { data } = Papa.parse<CsvRow>(csvData, {
      header: true,
      skipEmptyLines: true,
    });

    // Example usage with your data
    const hierarchicalData = csvToHierarchicalData(data, levels);
    console.log(JSON.stringify(hierarchicalData, null, 2));
    return hierarchicalData;
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

  return (
    <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
      <DialogTrigger asChild>
        <Button
          variant='outline'
          className='w-full justify-between text-left font-normal'
        >
          {selectedCount > 0 && (
            <Badge
              variant='secondary'
              className='ml-2 mr-2 bg-blue-100 hover:bg-blue-200 text-blue-800'
            >
              {selectedCount}
            </Badge>
          )}
          <ChevronDown className='h-4 w-4 opacity-50' />
        </Button>
      </DialogTrigger>
      <DialogContent className='sm:max-w-[550px] max-h-[80vh] overflow-hidden flex flex-col'>
        <DialogHeader>
          <DialogTitle>
            {`选择${cascaderParam.levels?.[0]?.name || '参数'}`}
          </DialogTitle>
        </DialogHeader>
        <div className='flex-1 overflow-auto py-4'>
          <TreeView
            data={treeData}
            showCheckboxes={true}
            searchPlaceholder='搜索...'
            selectionText='已选择'
            checkboxLabels={{
              check: '全选',
              uncheck: '取消全选',
            }}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
