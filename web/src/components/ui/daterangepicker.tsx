import React from 'react';
import dayjs from 'dayjs';
import { Calendar as CalendarIcon } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface DateRangePickerProps {
  dateRange: [Date | undefined, Date | undefined];
  setDateRange: (dateRange: [Date | undefined, Date | undefined]) => void;
  dateFormat?: string;
}

export function DateRangePicker({
  dateRange,
  setDateRange,
  dateFormat = 'YYYY-MM-DD',
}: DateRangePickerProps) {
  const [from, to] = dateRange;

  const [month, setMonth] = React.useState<number>(
    from ? dayjs(from).month() : dayjs().month()
  );
  const [year, setYear] = React.useState<number>(
    from ? dayjs(from).year() : dayjs().year()
  );

  const years = React.useMemo(() => {
    const currentYear = dayjs().year();
    // 年份范围：从当前年份向后推10年
    return Array.from(
      { length: currentYear - 2000 + 1 },
      (_, i) => currentYear - i
    );
  }, []);

  const months = React.useMemo(() => {
    if (year) {
      return Array.from({ length: 12 }, (_, i) => dayjs().year(year).month(i));
    }
    return [];
  }, [year]);

  React.useEffect(() => {
    if (from) {
      setMonth(dayjs(from).month());
      setYear(dayjs(from).year());
    }
  }, [from]);

  const handleYearChange = (selectedYear: string) => {
    const newYear = parseInt(selectedYear, 10);
    setYear(newYear);
  };

  const handleMonthChange = (selectedMonth: string) => {
    const newMonth = parseInt(selectedMonth, 10);
    setMonth(newMonth);
  };

  const formatDisplayDate = (date: Date | undefined) => {
    if (!date) return '';
    return dayjs(date).format(
      dateFormat === 'YYYYMMDD' ? 'YYYYMMDD' : 'YYYY-MM-DD'
    );
  };

  return (
    <div>
      <Popover>
        <PopoverTrigger asChild>
          <Button
            variant={'outline'}
            className={cn(
              'w-full justify-start text-left font-normal',
              !from && !to && 'text-muted-foreground'
            )}
          >
            <CalendarIcon className='mr-2 h-4 w-4' />
            {from || to ? (
              <span>
                {formatDisplayDate(from)} ~ {formatDisplayDate(to)}
              </span>
            ) : (
              <span>选择日期范围</span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className='w-auto p-0' align='start'>
          <div className='flex justify-between p-2 space-x-1'>
            <Select onValueChange={handleYearChange} value={year.toString()}>
              <SelectTrigger className='w-[120px]'>
                <SelectValue placeholder='年份' />
              </SelectTrigger>
              <SelectContent>
                {years.map((y: number) => (
                  <SelectItem key={y} value={y.toString()}>
                    {y}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select onValueChange={handleMonthChange} value={month.toString()}>
              <SelectTrigger className='w-[120px]'>
                <SelectValue placeholder='月份' />
              </SelectTrigger>
              <SelectContent>
                {months.map((m: dayjs.Dayjs, index: number) => (
                  <SelectItem key={index} value={index.toString()}>
                    {m.format('MMMM')}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Calendar
            mode='range'
            selected={{
              from,
              to,
            }}
            onSelect={(range) => {
              if (range?.from || range?.to) {
                setDateRange([range.from, range.to]);
              } else {
                setDateRange([undefined, undefined]);
              }
            }}
            month={dayjs().year(year).month(month).toDate()}
            onMonthChange={(newMonth: Date) => {
              setMonth(dayjs(newMonth).month());
              setYear(dayjs(newMonth).year());
            }}
            numberOfMonths={2}
            initialFocus
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
