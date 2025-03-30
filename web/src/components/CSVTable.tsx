import React, { useMemo } from 'react';
import { useReactTable, getCoreRowModel } from '@tanstack/react-table';
import Papa from 'papaparse';

export const CSVTable = React.memo(({ csvData }: { csvData: string }) => {
  // 使用 useMemo 缓存解析结果
  const parsedData = useMemo(() => {
    const results = Papa.parse(csvData, { header: true });
    return results.data.slice(0, 5); // 只取前5行
  }, [csvData]); // 仅在 csvData 变化时重新计算

  // 使用 useMemo 缓存列定义
  const columns = useMemo(() => {
    if (parsedData.length === 0) return [];
    return Object.keys(parsedData[0] as Record<string, unknown>).map((key) => ({
      id: key,
      header: key,
      accessorKey: key,
    }));
  }, [parsedData]);

  // 创建表格实例
  const table = useReactTable({
    data: parsedData,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className='max-w-full relative'>
      <div
        className='overflow-x-auto overflow-y-auto max-w-full'
        style={{ maxHeight: '400px' }}
      >
        <table
          className='border-collapse'
          style={{ tableLayout: 'auto', minWidth: '100%' }}
        >
          <thead className='sticky top-0 bg-white'>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((column) => (
                  <th
                    key={column.id}
                    className='border border-black p-2 text-left whitespace-nowrap'
                    style={{ minWidth: '120px' }}
                  >
                    {String(column.column.columnDef.header)}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className='border border-black p-2 whitespace-nowrap'
                    style={{ minWidth: '120px' }}
                  >
                    {String(cell.getValue() ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
});
