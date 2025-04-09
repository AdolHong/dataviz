import React from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { DateRanger } from '@/components/ui/dateranger';

export const Route = createFileRoute('/dev/daterangerdemo')({
  component: DateRangerDemoPage,
});

function DateRangerDemoPage() {
  const [selectedRange, setSelectedRange] = React.useState<{
    from: Date;
    to?: Date;
  }>({
    from: new Date(),
    to: undefined,
  });

  const handleRangeChange = (range: { from: Date; to?: Date }) => {
    setSelectedRange(range);
    console.log('选择的日期范围:', range);
  };

  return (
    <div className='p-8'>
      <h1 className='text-2xl font-bold mb-6'>日期范围选择器演示</h1>

      <div className='mb-8 max-w-xl'>
        <DateRanger
          onSelectRange={handleRangeChange}
          initialValue={selectedRange}
        />
      </div>

      <div className='p-4 border rounded-md bg-gray-50'>
        <h2 className='font-semibold mb-2'>已选择的日期范围:</h2>
        <p>开始日期: {selectedRange.from.toLocaleDateString('zh-CN')}</p>
        <p>
          结束日期:{' '}
          {selectedRange.to
            ? selectedRange.to.toLocaleDateString('zh-CN')
            : '未选择'}
        </p>
      </div>
    </div>
  );
}
