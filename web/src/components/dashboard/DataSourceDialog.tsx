import React, { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { type QueryStatus } from '@/lib/store/useQueryStatusStore';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { DataSource } from '@/types/models/dataSource';

interface DataSourceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  dataSource: DataSource | null;
  queryStatus: QueryStatus | null;
}

export function DataSourceDialog({
  open,
  onOpenChange,
  dataSource,
  queryStatus,
}: DataSourceDialogProps) {
  const [activeTab, setActiveTab] = useState<string>('details');

  if (!dataSource || !queryStatus) {
    return null;
  }
  console.log('queryStatus', queryStatus);

  const { queryResponse: response } = queryStatus;
  const hasError = response?.status === 'error';
  const demoData = response?.data?.demoData || '';
  const rowNumber = response?.data?.rowNumber || 0;
  const isCodeOrPython =
    response?.codeContext?.type === 'sql' ||
    response?.codeContext?.type === 'python';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle className='flex items-center gap-2'>
            <span>数据源: {dataSource.name}</span>
            <Badge
              variant={hasError ? 'destructive' : 'outline'}
              className='ml-2'
            >
              {response?.status || '未查询'}
            </Badge>
          </DialogTitle>
        </DialogHeader>

        <Tabs
          defaultValue='details'
          onValueChange={setActiveTab}
          value={activeTab}
        >
          <TabsList className='grid w-full grid-cols-3'>
            <TabsTrigger value='details'>基本信息</TabsTrigger>
            <TabsTrigger value='data'>数据预览</TabsTrigger>
            <TabsTrigger value='code'>代码查看</TabsTrigger>
          </TabsList>

          <TabsContent value='details' className='space-y-4 pt-4'>
            <div className='grid grid-cols-2 gap-4'>
              <div>
                <h3 className='text-sm font-medium text-muted-foreground'>
                  数据源ID
                </h3>
                <p className='text-sm'>{dataSource.id}</p>
              </div>
              <div>
                <h3 className='text-sm font-medium text-muted-foreground'>
                  别名
                </h3>
                <p className='text-sm'>{dataSource.alias}</p>
              </div>
              <div>
                <h3 className='text-sm font-medium text-muted-foreground'>
                  类型
                </h3>
                <p className='text-sm'>
                  {response?.codeContext?.type || '未知'}
                </p>
              </div>
              <div>
                <h3 className='text-sm font-medium text-muted-foreground'>
                  引擎
                </h3>
                <p className='text-sm'>
                  {response?.codeContext?.engine || '未知'}
                </p>
              </div>
              <div>
                <h3 className='text-sm font-medium text-muted-foreground'>
                  总行数
                </h3>
                <p className='text-sm'>{rowNumber}</p>
              </div>
              <div>
                <h3 className='text-sm font-medium text-muted-foreground'>
                  查询完成时间
                </h3>
                <p className='text-sm'>{response?.queryTime || '未知'}</p>
              </div>
            </div>

            {hasError && (
              <div className='mt-4'>
                <h3 className='text-sm font-medium text-destructive'>
                  错误信息
                </h3>
                <div className='mt-1 rounded-md bg-destructive/10 p-3 text-sm text-destructive'>
                  {response.error || response.message}
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value='data' className='pt-4'>
            {response?.data?.demoData ? (
              <div className='max-h-96 overflow-auto'>
                <pre className='text-xs rounded-md bg-muted p-4 font-mono'>
                  {demoData}
                </pre>
              </div>
            ) : (
              <div className='text-center p-4 text-muted-foreground'>
                无数据预览可用
              </div>
            )}
          </TabsContent>

          <TabsContent value='code' className='pt-4'>
            {isCodeOrPython ? (
              <Accordion type='single' collapsible className='w-full'>
                <AccordionItem value='code'>
                  <AccordionTrigger>查询代码</AccordionTrigger>
                  <AccordionContent>
                    <pre className='text-xs rounded-md bg-muted p-4 font-mono overflow-auto max-h-60'>
                      {response?.codeContext?.code || '无代码'}
                    </pre>
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem value='parsedCode'>
                  <AccordionTrigger>解析后代码</AccordionTrigger>
                  <AccordionContent>
                    <pre className='text-xs rounded-md bg-muted p-4 font-mono overflow-auto max-h-60'>
                      {response?.codeContext?.parsedCode || '无解析代码'}
                    </pre>
                  </AccordionContent>
                </AccordionItem>

                {response?.codeContext?.paramValues && (
                  <AccordionItem value='params'>
                    <AccordionTrigger>参数值</AccordionTrigger>
                    <AccordionContent>
                      <pre className='text-xs rounded-md bg-muted p-4 font-mono overflow-auto max-h-60'>
                        {JSON.stringify(
                          response.codeContext.paramValues,
                          null,
                          2
                        )}
                      </pre>
                    </AccordionContent>
                  </AccordionItem>
                )}
              </Accordion>
            ) : (
              <div className='text-center p-4 text-muted-foreground'>
                该数据源没有相关代码
              </div>
            )}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
