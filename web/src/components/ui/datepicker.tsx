import * as React from 'react';
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

interface DatePickerProps {
  date: Date | undefined;
  setDate: (date: Date | undefined) => void;
}

export function DatePicker({ date, setDate }: DatePickerProps) {
  const [month, setMonth] = React.useState<number>(
    date ? dayjs(date).month() : dayjs().month()
  );
  const [year, setYear] = React.useState<number>(
    date ? dayjs(date).year() : dayjs().year()
  );

  const years = React.useMemo(() => {
    const currentYear = dayjs().year();
    // 年份的开始结束
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
    if (date) {
      setMonth(dayjs(date).month());
      setYear(dayjs(date).year());
    }
  }, [date]);

  const handleYearChange = (selectedYear: string) => {
    const newYear = parseInt(selectedYear, 10);
    setYear(newYear);
    if (date) {
      const newDate = dayjs(date).year(newYear).toDate();
      setDate(newDate);
    }
  };

  const handleMonthChange = (selectedMonth: string) => {
    const newMonth = parseInt(selectedMonth, 10);
    setMonth(newMonth);
    if (date) {
      const newDate = dayjs(date).month(newMonth).toDate();
      setDate(newDate);
    } else {
      setDate(dayjs().year(year).month(newMonth).toDate());
    }
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant={'outline'}
          className={cn(
            'w-full justify-start text-left font-normal',
            !date && 'text-muted-foreground'
          )}
        >
          <CalendarIcon className='mr-2 h-4 w-4' />
          {date ? dayjs(date).format('YYYY-MM-DD') : <span>Pick a date</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent className='w-auto p-0' align='start'>
        <div className='flex justify-between p-2 space-x-1'>
          <Select onValueChange={handleYearChange} value={year.toString()}>
            <SelectTrigger className='w-[120px]'>
              <SelectValue placeholder='Year' />
            </SelectTrigger>
            <SelectContent>
              {years.map((y) => (
                <SelectItem key={y} value={y.toString()}>
                  {y}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select onValueChange={handleMonthChange} value={month.toString()}>
            <SelectTrigger className='w-[120px]'>
              <SelectValue placeholder='Month' />
            </SelectTrigger>
            <SelectContent>
              {months.map((m, index) => (
                <SelectItem key={index} value={index.toString()}>
                  {m.format('MMMM')}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Calendar
          mode='single'
          selected={date}
          onSelect={setDate}
          month={dayjs().year(year).month(month).toDate()}
          onMonthChange={(newMonth) => {
            setMonth(dayjs(newMonth).month());
            setYear(dayjs(newMonth).year());
          }}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  );
}
