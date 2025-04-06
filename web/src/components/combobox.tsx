'use client';

import { useEffect, useState } from 'react';
import { Check, ChevronsUpDown, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { toast } from 'sonner';

interface ComboboxProps {
  options: Record<string, string>[];
  value: string | string[];
  onValueChange: (value: string | string[]) => void;
  placeholder?: string;
  mode?: 'single' | 'multiple';
  disabled?: boolean;
  terminateCancelSelect?: (value: string) => boolean;
  displayNum?: number;
  clearAble?: boolean;
}

export function Combobox({
  options,
  value,
  onValueChange,
  placeholder = '默认值为空',
  mode = 'single',
  disabled = false,
  terminateCancelSelect,
  displayNum = 5,
  clearAble = false,
}: ComboboxProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (
      !clearAble &&
      (!value || (Array.isArray(value) && value.length === 0)) &&
      options.length > 0
    ) {
      const firstOptionValue = options[0].value;
      onValueChange(mode === 'single' ? firstOptionValue : [firstOptionValue]);
    }
  }, [options, clearAble, value, mode]);

  useEffect(() => {
    options.forEach((option) => {
      const value = option['value'];
      const key = option['key'];
      if (!key || key === '') {
        toast.error('选项必须包含key');
      }
      if (!value || value === '') {
        toast.error('选项必须包含value');
      }
    });
  }, [options]);

  const handleSelect = (currentValue: string) => {
    // 判断当前的值是否可以被取消选中
    if (terminateCancelSelect && terminateCancelSelect(currentValue)) {
      if (
        (mode === 'single' && currentValue === value) ||
        (mode === 'multiple' &&
          Array.isArray(value) &&
          value.includes(currentValue))
      ) {
        return;
      }
    }

    if (mode === 'single') {
      if (!clearAble && currentValue === value) {
        return;
      }
      onValueChange(currentValue === value ? '' : currentValue);
      setOpen(false);
    } else {
      // 多选模式
      const currentValues = Array.isArray(value) ? value : [];

      if (
        !clearAble &&
        currentValues.length === 1 &&
        currentValues.includes(currentValue)
      ) {
        return;
      }

      const newValues = currentValues.includes(currentValue)
        ? currentValues.filter((v) => v !== currentValue)
        : [...currentValues, currentValue];

      onValueChange(newValues);
    }
  };

  // 新增：全选/清空功能
  const handleSelectAll = () => {
    if (mode === 'multiple') {
      const allValues = options.map((option) => option.value);
      const currentValues = Array.isArray(value) ? value : [];

      // 如果当前选中的值与全部值相同，则清空；否则全选
      const newValues =
        currentValues.length === allValues.length ? [] : allValues;

      onValueChange(newValues);
    }
  };

  const displayValue =
    mode === 'single'
      ? (value as string) || placeholder
      : (value as string[]).length > 0
        ? (value as string[]).length <= displayNum
          ? (value as string[]).join(', ')
          : (value as string[]).length === options.length
            ? '全部'
            : `已选 ${(value as string[]).length} 项`
        : placeholder;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant='outline'
          role='combobox'
          aria-expanded={open}
          className='w-full justify-between'
          disabled={disabled || options.length === 0}
        >
          <div className='truncate max-w-[calc(100%-40px)]'>{displayValue}</div>
          <ChevronsUpDown className='ml-2 h-4 w-4 shrink-0 opacity-50' />
        </Button>
      </PopoverTrigger>

      <PopoverContent className='w-full p-0'>
        <Command>
          <CommandInput
            placeholder='搜索选项...'
            disabled={options.length === 0}
          />

          {mode === 'multiple' && (
            <div className='flex justify-end p-2'>
              <Button
                className='w-full'
                size='sm'
                variant='outline'
                onClick={handleSelectAll}
                disabled={options.length === 0}
              >
                {value &&
                Array.isArray(value) &&
                value.length === options.length
                  ? '清空'
                  : '全选'}
              </Button>
            </div>
          )}

          <CommandList>
            <CommandEmpty>没有找到选项</CommandEmpty>
            <CommandGroup>
              {options.map((option) => (
                <CommandItem
                  key={option.key}
                  value={option.value}
                  onSelect={() => handleSelect(option.value)}
                >
                  <Check
                    className={cn(
                      'mr-2 h-4 w-4',
                      mode === 'single'
                        ? value === option.value
                          ? 'opacity-100'
                          : 'opacity-0'
                        : Array.isArray(value) && value.includes(option.value)
                          ? 'opacity-100'
                          : 'opacity-0'
                    )}
                  />
                  {option.value}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
