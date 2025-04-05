import { type Layout, type LayoutItem } from '@/types/models/layout';
import { type Report } from '@/types/models/report';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { type DataSource } from '@/types/models/dataSource';
import { type Artifact } from '@/types/models/artifact';
import { LayoutGridItem } from './LayoutGridItem';

import {
  useTabQueryStatusStore,
  type QueryStatus,
} from '@/lib/store/useTabQueryStatusStore';

interface LayoutGridProps {
  report: Report;
  activeTabId: string;
}

export function LayoutGrid({ report, activeTabId }: LayoutGridProps) {
  if (!report || activeTabId === '') {
    return <></>;
  }

  const queryStatus = useTabQueryStatusStore((state) =>
    state.getQueryStatusByTabId(activeTabId)
  );

  // 预处理 artifacts 和 dataSources
  const processedItems = useMemo(() => {
    return report.layout.items.map((layoutItem) => {
      const artifact = report.artifacts.find(
        (artifact) => artifact.id === layoutItem.id
      );

      const dependentDataSources: string[] = artifact
        ? artifact.dependencies
            .map((dependency) => {
              const dataSource = report.dataSources.find(
                (dataSource) => dataSource.alias === dependency
              );
              return dataSource ? dataSource.id : '';
            })
            .filter(Boolean)
        : [];

      const dependentQueryStatus: Record<string, QueryStatus> = Object.keys(
        queryStatus
      )
        .filter((key) => dependentDataSources.includes(key))
        .reduce(
          (acc, key) => {
            acc[key] = queryStatus[key];
            return acc;
          },
          {} as Record<string, QueryStatus>
        );

      return {
        layoutItem,
        artifact,
        strDependentQueryStatus: JSON.stringify(dependentQueryStatus),
        report,
      };
    });
  }, [report.artifacts, report.dataSources, queryStatus, report]);

  // 渲染函数使用 useCallback
  const renderLayoutGridItem = useCallback(
    (props: {
      layoutItem: LayoutItem;
      artifact: Artifact | undefined;
      strDependentQueryStatus: string;
      report: Report;
    }) => {
      return (
        <LayoutGridItem key={props.layoutItem.id} {...props} report={report} />
      );
    },
    [report]
  );

  return (
    <>
      <div
        className='grid gap-6 w-full'
        style={{
          gridTemplateColumns: `repeat(${report.layout.columns}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${report.layout.rows}, minmax(200px, auto))`,
          gridAutoFlow: 'dense',
        }}
      >
        {processedItems.map((item) => renderLayoutGridItem(item))}
      </div>
    </>
  );
}
