'use client';

import * as React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Calendar } from './calendar';
import { Button } from './button';
import { cn } from '@/lib/utils';
import { Popover, PopoverContent, PopoverTrigger } from './popover';

interface DateRangerProps {
  onSelectRange?: (range: { from: Date; to?: Date }) => void;
  className?: string;
  initialValue?: { from: Date; to?: Date };
}

export function DateRanger({
  onSelectRange,
  className,
  initialValue,
}: DateRangerProps) {
  const [date, setDate] = React.useState<Date>(new Date());
  const [selectedRange, setSelectedRange] = React.useState<{
    from: Date;
    to?: Date;
  }>(initialValue || { from: new Date(), to: undefined });
  const [isOpen, setIsOpen] = React.useState(false);

  // 处理月份切换
  const handlePrevious = () => {
    const prevMonth = new Date(date);
    prevMonth.setMonth(prevMonth.getMonth() - 2);
    setDate(prevMonth);
  };

  const handleNext = () => {
    const nextMonth = new Date(date);
    nextMonth.setMonth(nextMonth.getMonth() + 2);
    setDate(nextMonth);
  };

  // 生成月份标题
  const getMonthTitle = (date: Date, offset: number = 0): string => {
    const monthDate = new Date(date);
    monthDate.setMonth(monthDate.getMonth() + offset);
    return monthDate.toLocaleDateString('en-US', {
      month: 'long',
      year: 'numeric',
    });
  };

  // 处理日期选择
  const handleSelect = (value: { from?: Date; to?: Date } | undefined) => {
    if (value?.from) {
      const newRange = { from: value.from, to: value.to };
      setSelectedRange(newRange);
      if (onSelectRange) {
        onSelectRange(newRange);
      }
    }
  };

  // 切换年份或月份的弹出菜单
  const MonthYearSelector = ({
    date,
    offset,
  }: {
    date: Date;
    offset: number;
  }) => {
    const monthDate = new Date(date);
    monthDate.setMonth(monthDate.getMonth() + offset);
    const currentMonth = monthDate.getMonth();
    const currentYear = monthDate.getFullYear();

    return (
      <Popover>
        <PopoverTrigger asChild>
          <Button className='border border-red-500 bg-white text-black hover:bg-gray-100 px-6'>
            {getMonthTitle(date, offset)}
          </Button>
        </PopoverTrigger>
        <PopoverContent className='w-auto p-0'>
          <div className='p-2'>
            <div className='mb-2 font-medium'>选择年份</div>
            <div className='grid grid-cols-3 gap-2'>
              {Array.from({ length: 6 }, (_, i) => currentYear - 3 + i).map(
                (year) => (
                  <Button
                    key={year}
                    variant={year === currentYear ? 'default' : 'outline'}
                    size='sm'
                    onClick={() => {
                      const newDate = new Date(date);
                      newDate.setFullYear(year);
                      setDate(newDate);
                    }}
                  >
                    {year}
                  </Button>
                )
              )}
            </div>

            <div className='mt-4 mb-2 font-medium'>选择月份</div>
            <div className='grid grid-cols-3 gap-2'>
              {Array.from({ length: 12 }, (_, i) => i).map((month) => (
                <Button
                  key={month}
                  variant={month === currentMonth ? 'default' : 'outline'}
                  size='sm'
                  onClick={() => {
                    const newDate = new Date(date);
                    newDate.setMonth(month - offset);
                    setDate(newDate);
                  }}
                >
                  {new Date(2000, month, 1).toLocaleDateString('en-US', {
                    month: 'short',
                  })}
                </Button>
              ))}
            </div>
          </div>
        </PopoverContent>
      </Popover>
    );
  };

  return (
    <div className={cn('border rounded-md shadow-sm', className)}>
      <div className='flex justify-between items-center p-2 border-b'>
        <Button variant='ghost' size='icon' onClick={handlePrevious}>
          <ChevronLeft className='h-4 w-4' />
        </Button>

        <div className='flex gap-4 justify-center flex-1'>
          {/* 左侧月份标题（红色按钮区域） */}
          <MonthYearSelector date={date} offset={0} />

          {/* 右侧月份标题（红色按钮区域） */}
          <MonthYearSelector date={date} offset={1} />
        </div>

        <Button variant='ghost' size='icon' onClick={handleNext}>
          <ChevronRight className='h-4 w-4' />
        </Button>
      </div>

      <div className='p-3'>
        <Calendar
          mode='range'
          selected={selectedRange}
          onSelect={handleSelect}
          numberOfMonths={2}
          defaultMonth={date}
          showOutsideDays
        />
      </div>
    </div>
  );
}
