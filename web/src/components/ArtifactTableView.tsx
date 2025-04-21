import React, { useMemo } from 'react';
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  getPaginationRowModel,
  getSortedRowModel,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { ArrowUpDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Download, MoreHorizontal } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { saveAs } from 'file-saver';
import Papa from 'papaparse';

interface ArtifactTableViewProps {
  data: string; // JSON string from ArtifactTableDataContext
  title?: string;
  fileName?: string;
  showExport?: boolean;
}

export const ArtifactTableView: React.FC<ArtifactTableViewProps> = ({
  data,
  title,
  fileName = 'table-data',
  showExport = true,
}) => {
  // 解析JSON数据
  const parsedData = useMemo(() => {
    try {
      return JSON.parse(data) as Record<string, any>[];
    } catch (error) {
      console.error('数据解析错误:', error);
      return [];
    }
  }, [data]);

  const [sorting, setSorting] = React.useState<SortingState>([]);

  // 基于第一行数据动态生成列定义
  const columns = useMemo(() => {
    if (!parsedData.length) return [];

    return Object.keys(parsedData[0]).map((key) => {
      // 判断列的数据类型
      const firstValue = parsedData.find((row) => row[key] !== null)?.[key];
      const isNumber = typeof firstValue === 'number';
      const isDate = !isNumber && !isNaN(Date.parse(String(firstValue)));
      const isBoolean = typeof firstValue === 'boolean';

      return {
        accessorKey: key,
        header: ({ column }) => {
          return (
            <Button
              variant='ghost'
              onClick={() =>
                column.toggleSorting(column.getIsSorted() === 'asc')
              }
              className='whitespace-nowrap'
            >
              {key}
              <ArrowUpDown className='ml-2 h-4 w-4' />
            </Button>
          );
        },
        cell: ({ row }) => {
          const value = row.getValue(key);

          // 根据数据类型格式化单元格
          if (value === null || value === undefined) {
            return <span className='text-muted-foreground'>-</span>;
          } else if (isBoolean) {
            return value ? '是' : '否';
          } else if (isDate) {
            try {
              const date = new Date(value as string);
              return date.toLocaleString('zh-CN');
            } catch {
              return String(value);
            }
          } else if (isNumber) {
            // 使用千分位格式化数字
            return new Intl.NumberFormat('zh-CN').format(value as number);
          } else {
            return String(value);
          }
        },
      } as ColumnDef<Record<string, any>>;
    });
  }, [parsedData]);

  const table = useReactTable({
    data: parsedData,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: {
      sorting,
    },
  });

  // 导出CSV
  const handleExportCSV = () => {
    try {
      const csv = Papa.unparse(parsedData);
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      saveAs(blob, `${fileName}.csv`);
    } catch (error) {
      console.error('导出CSV错误:', error);
    }
  };

  // 导出JSON
  const handleExportJSON = () => {
    try {
      const json = JSON.stringify(parsedData, null, 2);
      const blob = new Blob([json], {
        type: 'application/json;charset=utf-8;',
      });
      saveAs(blob, `${fileName}.json`);
    } catch (error) {
      console.error('导出JSON错误:', error);
    }
  };

  if (!parsedData.length) {
    return (
      <div className='text-center py-4 text-muted-foreground'>暂无数据</div>
    );
  }

  return (
    <Card className='w-full h-full overflow-hidden'>
      {title && (
        <CardHeader className='px-6 py-4 flex flex-row items-center justify-between space-y-0'>
          <CardTitle className='text-base font-medium'>{title}</CardTitle>
          {showExport && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant='ghost' size='sm' className='h-8 w-8 p-0'>
                  <MoreHorizontal className='h-4 w-4' />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align='end'>
                <DropdownMenuItem onClick={handleExportCSV}>
                  <Download className='mr-2 h-4 w-4' />
                  <span>导出 CSV</span>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleExportJSON}>
                  <Download className='mr-2 h-4 w-4' />
                  <span>导出 JSON</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </CardHeader>
      )}
      <CardContent className={`p-0 ${title ? '' : 'pt-4'}`}>
        <div className='overflow-auto max-h-[500px]'>
          <div className='rounded-md border'>
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead key={header.id}>
                        {header.isPlaceholder
                          ? null
                          : flexRender(
                              header.column.columnDef.header,
                              header.getContext()
                            )}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {table.getRowModel().rows?.length ? (
                  table.getRowModel().rows.map((row) => (
                    <TableRow
                      key={row.id}
                      data-state={row.getIsSelected() && 'selected'}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id}>
                          {flexRender(
                            cell.column.columnDef.cell,
                            cell.getContext()
                          )}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell
                      colSpan={columns.length}
                      className='h-24 text-center'
                    >
                      暂无数据
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </div>

        <div className='flex items-center justify-end space-x-2 py-4 px-4'>
          <Button
            variant='outline'
            size='sm'
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            <ChevronLeft className='h-4 w-4' />
          </Button>
          <span className='text-sm text-muted-foreground'>
            第 {table.getState().pagination.pageIndex + 1} 页， 共{' '}
            {table.getPageCount()} 页
          </span>
          <Button
            variant='outline'
            size='sm'
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            <ChevronRight className='h-4 w-4' />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};
