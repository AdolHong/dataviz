import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

export function DashboardPage() {
  return (
    <div className='flex h-screen'>
      {/* 左侧导航栏 */}
      <div className='w-64 border-r bg-background p-4 overflow-auto'>
        <div className='flex items-center justify-between mb-4'>
          <h2 className='text-lg font-semibold'>文件夹</h2>
          <Button variant='outline' size='sm'>
            新建
          </Button>
        </div>
        <div className='space-y-1'>
          {/* 后续添加导航菜单 */}
          <div className='p-2 rounded-md hover:bg-accent cursor-pointer'>
            示例文件夹
          </div>
        </div>
      </div>

      {/* 右侧内容区 */}
      <div className='flex-1 overflow-auto'>
        <div className='container mx-auto p-6 space-y-6'>
          {/* 标题和描述 */}
          <div>
            <h1 className='text-3xl font-bold'>报表标题</h1>
            <p className='text-muted-foreground'>报表描述信息</p>
          </div>

          {/* 参数区域 */}
          <Card>
            <CardHeader className='pb-3'>
              <CardTitle>查询参数</CardTitle>
              <CardDescription>设置过滤条件</CardDescription>
            </CardHeader>
            <CardContent className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4'>
              <div className='space-y-2'>
                <label className='text-sm font-medium'>区域</label>
                <Input placeholder='华东' />
              </div>
              <div className='space-y-2'>
                <label className='text-sm font-medium'>分类</label>
                <Input placeholder='电子产品' />
              </div>
              <div className='space-y-2'>
                <label className='text-sm font-medium'>日期</label>
                <Input placeholder='2023-01-30' />
              </div>
              <div className='space-y-2'>
                <label className='text-sm font-medium'>最低价格</label>
                <Input placeholder='100' />
              </div>
            </CardContent>
            <div className='flex justify-end px-6 pb-6'>
              <Button>查询</Button>
            </div>
          </Card>

          {/* 展示区域 */}
          <div className='space-y-6'>
            <Tabs defaultValue='数据可视化区域' className='w-full'>
              <TabsList className='mb-4'>
                <TabsTrigger value='数据可视化区域'>数据可视化区域</TabsTrigger>
                <TabsTrigger value='区域销量趋势图'>区域销量趋势图</TabsTrigger>
                <TabsTrigger value='3'>自定义区域</TabsTrigger>
              </TabsList>
              <TabsContent value='数据可视化区域'>
                <Card>
                  <CardHeader>
                    <CardTitle>数据可视化区域</CardTitle>
                    <CardDescription>
                      显示根据 layout 定义的数据可视化内容
                    </CardDescription>
                  </CardHeader>
                  <CardContent className='h-[400px] border-2 border-dashed border-muted-foreground/20 rounded-md flex items-center justify-center'>
                    <p className='text-muted-foreground'>
                      数据可视化内容将显示在这里
                    </p>
                  </CardContent>
                </Card>
              </TabsContent>
              <TabsContent value='区域销量趋势图'>
                <Card>
                  <CardHeader>
                    <CardTitle>区域销量趋势图</CardTitle>
                    <CardDescription>展示各区域销量变化趋势</CardDescription>
                  </CardHeader>
                  <CardContent className='h-[400px] border-2 border-dashed border-muted-foreground/20 rounded-md flex items-center justify-center'>
                    <p className='text-muted-foreground'>区域销量趋势图内容</p>
                  </CardContent>
                </Card>
              </TabsContent>
              <TabsContent value='3'>
                <Card>
                  <CardHeader>
                    <CardTitle>自定义区域</CardTitle>
                    <CardDescription>可自定义内容的展示区域</CardDescription>
                  </CardHeader>
                  <CardContent className='h-[400px] border-2 border-dashed border-muted-foreground/20 rounded-md flex items-center justify-center'>
                    <p className='text-muted-foreground'>
                      自定义内容将显示在这里
                    </p>
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </div>
    </div>
  );
}
