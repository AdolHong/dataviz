import React from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { type Layout, type LayoutItem } from '@/types/models/layout';
import { cn } from '@/lib/utils';

interface LayoutGridProps {
  layout: Layout;
  onItemClick?: (itemId: string) => void;
}

export function LayoutGrid({ layout, onItemClick }: LayoutGridProps) {
  // 创建一个二维数组表示网格
  const grid = Array(layout.rows)
    .fill(null)
    .map(() => Array(layout.columns).fill(null));

  // 将每个项目放入网格中
  layout.items.forEach((item) => {
    for (let y = item.y; y < item.y + item.height && y < layout.rows; y++) {
      for (let x = item.x; x < item.x + item.width && x < layout.columns; x++) {
        grid[y][x] = item.id;
      }
    }
  });

  // 渲染具体的网格项内容
  const renderGridItem = (item: LayoutItem) => {
    // 计算网格项的样式，包括起始位置和跨度
    const itemStyle = {
      gridColumn: `${item.x + 1} / span ${item.width}`,
      gridRow: `${item.y + 1} / span ${item.height}`,
    };

    return (
      <div
        key={item.id}
        className={cn('min-h-60')}
        style={itemStyle}
        onClick={() => onItemClick?.(item.id)}
      >
        <Card className='h-full overflow-hidden shadow-sm hover:shadow-md transition-shadow duration-300'>
          <CardHeader className='pb-2'>
            <CardTitle className='text-lg font-medium'>{item.title}</CardTitle>
          </CardHeader>
          <CardContent className='p-0 h-[calc(100%-3.5rem)]'>
            <div className='flex items-center justify-center h-full border-t p-4'>
              <div className='text-muted-foreground text-sm'>
                {item.title} 内容
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  };

  return (
    <div
      className='grid gap-4 w-full'
      style={{
        gridTemplateColumns: `repeat(${layout.columns}, minmax(0, 1fr))`,
        gridTemplateRows: `repeat(${layout.rows}, minmax(200px, auto))`,
        gridAutoFlow: 'dense',
      }}
    >
      {layout.items.map((item) => renderGridItem(item))}
    </div>
  );
}

// 创建占位图表组件
export function PlaceholderChart({ title }: { title: string }) {
  return (
    <div className='flex flex-col items-center justify-center h-full bg-muted/20 rounded-md border border-dashed border-border p-4'>
      <div className='text-muted-foreground text-sm'>{title}</div>
    </div>
  );
}
