import { type Report } from '@/types/models/report';
import { LayoutGridItem } from './LayoutGridItem';
import {
  useQueryStatusStore,
  type QueryStatus,
} from '@/lib/store/useQueryStatusStore';

interface LayoutGridProps {
  report: Report;
  activeTabId: string;
}

export function LayoutGrid({ report, activeTabId }: LayoutGridProps) {
  if (!report || activeTabId === '') {
    return <></>;
  }

  const queryStatus = useQueryStatusStore((state) =>
    state.getQueryStatusByTabId(activeTabId)
  );

  if (!queryStatus) {
    return <></>;
  }

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
        {report.layout.items.map((item) => {
          const artifact = report.artifacts.find(
            (artifact) => artifact.id === item.id
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

          console.info('hi, layoutgrid');
          return (
            <LayoutGridItem
              key={item.id}
              layoutItem={item}
              artifact={artifact}
              strDependentQueryStatus={JSON.stringify(dependentQueryStatus)}
              report={report}
            />
          );
        })}
      </div>
    </>
  );
}
