import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { useArtifactDialogStore } from '@/lib/store/useArtifactDialogStore';

export function ArtifactResponseDialog() {
  const { isOpen, artifact, artifactResponse, closeDialog } =
    useArtifactDialogStore();
  const [activeTab, setActiveTab] = useState<string>('details');

  if (!artifact || !artifactResponse) {
    return null;
  }

  const hasError = artifactResponse.status === 'error';
  const dependentDfs = Object.entries(
    artifactResponse.codeContext.dfAliasUniqueIds
  );

  return (
    <Dialog open={isOpen} onOpenChange={closeDialog}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle className='flex items-center gap-2'>
            <span>可视化组件: {artifact.title}</span>
            <Badge
              variant={hasError ? 'destructive' : 'outline'}
              className='ml-2'
            >
              {artifactResponse.status || '未执行'}
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
            <TabsTrigger value='params'>参数信息</TabsTrigger>
            <TabsTrigger value='code'>代码查看</TabsTrigger>
          </TabsList>

          <TabsContent value='details' className='space-y-4 pt-4'>
            <div className='grid grid-cols-2 gap-4'>
              <div>
                <h3 className='text-sm font-medium text-muted-foreground'>
                  组件ID
                </h3>
                <p className='text-sm'>{artifact.id}</p>
              </div>
              <div>
                <h3 className='text-sm font-medium text-muted-foreground'>
                  查询时间
                </h3>
                <p className='text-sm'>
                  {artifactResponse.queryTime || '未知'}
                </p>
              </div>
              <div>
                <h3 className='text-sm font-medium text-muted-foreground'>
                  引擎
                </h3>
                <p className='text-sm'>
                  {artifactResponse.codeContext.engine || '默认'}
                </p>
              </div>
              <div>
                <h3 className='text-sm font-medium text-muted-foreground'>
                  依赖数据源
                </h3>
                <div className='text-sm'>
                  {dependentDfs.length > 0 ? (
                    <ul className='list-disc pl-4'>
                      {dependentDfs.map(([alias, id]) => (
                        <li key={alias}>
                          {alias} (ID: {id})
                        </li>
                      ))}
                    </ul>
                  ) : (
                    '无依赖数据源'
                  )}
                </div>
              </div>
            </div>

            {/* 输出信息 */}
            <div className='mt-4'>
              <h3 className='text-sm font-medium text-muted-foreground'>
                python输出信息(即print)
              </h3>
              <div className='mt-1 rounded-md bg-muted p-3 text-sm overflow-auto max-h-40'>
                <pre className='whitespace-pre-wrap'>
                  {artifactResponse.message || '无输出信息'}
                </pre>
              </div>
            </div>

            {/* 错误信息 */}
            {hasError && (
              <div className='mt-4'>
                <h3 className='text-sm font-medium text-destructive'>
                  错误信息
                </h3>
                <div className='mt-1 rounded-md bg-destructive/10 p-3 text-sm text-destructive overflow-auto max-h-40'>
                  <pre className='whitespace-pre-wrap'>
                    {artifactResponse.error || '未知错误'}
                  </pre>
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value='params' className='pt-4'>
            <div className='space-y-4'>
              {/* 普通参数 */}
              <div>
                <h3 className='text-sm font-medium mb-2'>普通参数</h3>
                {Object.keys(artifactResponse.codeContext.plainParamValues)
                  .length > 0 ? (
                  <div className='rounded-md bg-muted p-4'>
                    <pre className='text-xs font-mono overflow-auto max-h-40'>
                      {JSON.stringify(
                        artifactResponse.codeContext.plainParamValues,
                        null,
                        2
                      )}
                    </pre>
                  </div>
                ) : (
                  <div className='text-sm text-muted-foreground'>
                    无普通参数
                  </div>
                )}
              </div>

              {/* 级联参数 */}
              <div>
                <h3 className='text-sm font-medium mb-2'>级联参数</h3>
                {Object.keys(artifactResponse.codeContext.cascaderParamValues)
                  .length > 0 ? (
                  <div className='rounded-md bg-muted p-4'>
                    <div className='space-y-2'>
                      {Object.entries(
                        artifactResponse.codeContext.cascaderParamValues
                      ).map(([key, value]) => {
                        const [dfAlias, column] = key.split(',');
                        return (
                          <div
                            key={key}
                            className='border-b pb-2 last:border-b-0 last:pb-0'
                          >
                            <div className='font-medium'>
                              数据源:{' '}
                              <span className='font-normal'>{dfAlias}</span> |
                              列名:{' '}
                              <span className='font-normal'>{column}</span>
                            </div>
                            <div className='font-medium mt-1'>
                              选中值:
                              <span className='font-normal ml-2'>
                                {Array.isArray(value)
                                  ? value.join(', ')
                                  : value}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className='text-sm text-muted-foreground'>
                    无级联参数
                  </div>
                )}
              </div>
            </div>
          </TabsContent>

          <TabsContent value='code' className='pt-4'>
            <pre className='text-xs rounded-md bg-muted p-4 font-mono overflow-auto max-h-60'>
              {artifactResponse.codeContext.pyCode || '无代码'}
            </pre>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
