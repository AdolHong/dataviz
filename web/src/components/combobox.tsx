'use client';

import { useEffect, useState } from 'react';
import { Check, ChevronsUpDown } from 'lucide-react';
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
}

export function Combobox({
  options,
  value,
  onValueChange,
  placeholder = '默认值为空',
  mode = 'single',
  disabled = false,
}: ComboboxProps) {
  const [open, setOpen] = useState(false);

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
    if (mode === 'single') {
      // 单选模式
      onValueChange(currentValue === value ? '' : currentValue);
      setOpen(false);
    } else {
      // 多选模式
      const currentValues = Array.isArray(value) ? value : [];
      const newValues = currentValues.includes(currentValue)
        ? currentValues.filter((v) => v !== currentValue)
        : [...currentValues, currentValue];

      onValueChange(newValues);
    }
  };

  const displayValue =
    mode === 'single'
      ? (value as string) || placeholder
      : (value as string[]).length > 0
        ? (value as string[]).join(', ')
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
          {displayValue}
          <ChevronsUpDown className='ml-2 h-4 w-4 shrink-0 opacity-50' />
        </Button>
      </PopoverTrigger>
      <PopoverContent className='w-full p-0'>
        <Command>
          <CommandInput
            placeholder='搜索选项...'
            disabled={options.length === 0}
          />
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
