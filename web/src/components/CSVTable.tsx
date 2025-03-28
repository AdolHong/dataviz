import { useReactTable, getCoreRowModel } from '@tanstack/react-table';
import Papa from 'papaparse';

export const CSVTable = ({ csvData }: { csvData: string }) => {
  // 解析 CSV 数据
  const results = Papa.parse(csvData, { header: true });
  const parsedData = results.data.slice(0, 10); // 只取前10行

  // 定义列
  const columns = Object.keys(parsedData[0] || {}).map((key) => ({
    header: key,
    accessor: key, // 访问器
  }));

  // 创建表格实例
  const table = useReactTable({
    data: parsedData,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div style={{ overflowX: 'auto', maxHeight: '400px' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((column) => (
                <th
                  key={column.id}
                  style={{ border: '1px solid black', padding: '8px' }}
                >
                  {column.header}
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
                  style={{ border: '1px solid black', padding: '8px' }}
                >
                  {cell.getValue()}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default CSVTable;
