import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

import { Filter, Database, BarChart2, Info } from 'lucide-react';
import { toast } from 'sonner';

import type {
  DataSource,
  Layout,
  Parameter,
  Artifact,
  EngineChoices,
} from '@/types';

import TabDataSource from './TabDataSource';
import TabFilter from './TabFilter';
import TabArtifact from './TabArtifact';
import TabBasicInfo from './TabBasicInfo';

import {
  type AliasRelianceMap,
  createAliasRelianceMap,
  updateAliasRelianceMapByArtifact,
} from '@/types/models/aliasRelianceMap';

import {
  addItem as addLayoutItem,
  removeEmptyRowsAndColumns,
} from '@/types/models/layout';
import {
  addDataSource,
  deleteDataSource,
  editDataSource,
} from '@/types/models/report';

interface EditModalProps {
  open: boolean;
  onClose: () => void;
  reportId: string;
}

const EditModal = ({ open, onClose, reportId }: EditModalProps) => {
  // 构造 demo 数据
  const demoReport = {
    id: 'report-1',
    title: '销售报表',
    description: '这是一个销售数据的示例报表',
    dataSources: [
      {
        id: 'source-1',
        name: '主数据',
        alias: 'df_sales',
        executor: { type: 'sql', engine: 'default' },
        code: '',
      },
      {
        id: 'source-2',
        name: '外部数据',
        alias: 'df_external',
        executor: { type: 'python', engine: 'default' },
        code: '',
      },
    ],
    parameters: [
      {
        id: 'p1',
        name: 'start_date',
        alias: '开始日期', // 可选字段
        description: '选择开始日期',
        config: {
          type: 'single_select',
          choices: ['2023-01-01', '2023-01-02', '2023-01-03'],
          default: '2023-01-01',
        },
      },
      {
        id: 'p2',
        name: 'end_date',
        alias: '结束日期', // 可选字段
        description: '选择结束日期',
        config: {
          type: 'single_select',
          choices: ['2023-01-04', '2023-01-05', '2023-01-06'],
          default: '2023-01-04',
        },
      },
    ],
    artifacts: [
      {
        id: 'artifact-1',
        title: '销售趋势',
        code: 'line',
        dependencies: ['df_sales'],
        executor: { type: 'python', engine: 'pandas' },
      },
      {
        id: 'artifact-2',
        title: '销售占比',
        code: 'pie',
        dependencies: ['df_external'],
        executor: { type: 'python', engine: 'pandas' },
      },
      {
        id: 'artifact-3',
        title: '销售明细',
        code: 'pie',
        dependencies: ['df_external'],
        executor: { type: 'python', engine: 'pandas' },
      },
      {
        id: 'artifact-4',
        title: '新增图表1',
        code: 'pie',
        dependencies: ['df_sales', 'df_external'],
        executor: { type: 'python', engine: 'pandas' },
      },
      {
        id: 'artifact-5',
        title: '新增图表2',
        code: 'pie',
        dependencies: ['df_sales'],
        executor: { type: 'python', engine: 'pandas' },
      },
    ],
    layout: {
      columns: 3,
      rows: 2,
      items: [
        {
          id: 'artifact-1',
          title: '销售趋势',
          width: 1,
          height: 1,
          x: 0,
          y: 0,
        },
        {
          id: 'artifact-2',
          title: '销售占比',
          width: 1,
          height: 1,
          x: 1,
          y: 0,
        },
        {
          id: 'artifact-3',
          title: '销售明细',
          width: 1,
          height: 1,
          x: 2,
          y: 0,
        },
        {
          id: 'artifact-4',
          title: '新增图表1',
          width: 1,
          height: 1,
          x: 0,
          y: 1,
        },
        {
          id: 'artifact-5',
          title: '新增图表2',
          width: 1,
          height: 1,
          x: 1,
          y: 1,
        },
      ],
    },
  };

  const demoDataSourceEngineChoices: EngineChoices = {
    sql: ['default', 'starrocks'],
    python: ['default', '3.9'],
  };

  const demoArtifactEngineChoices: EngineChoices = ['default'];

  // report的参数
  const [dataSources, setDataSources] = useState<DataSource[]>(
    demoReport.dataSources
  );
  const [parameters, setParameters] = useState<Parameter[]>(
    demoReport.parameters
  );
  const [artifacts, setArtifacts] = useState<Artifact[]>(demoReport.artifacts);
  const [layout, setLayout] = useState<Layout>(demoReport.layout);
  const [activeTab, setActiveTab] = useState('info');

  // 创建一个对象来存储 alias 和对应的 artifact.id 列表
  const [aliasRelianceMap, setAliasRelianceMap] = useState<AliasRelianceMap>(
    createAliasRelianceMap(demoReport.dataSources, demoReport.artifacts)
  );

  // 确认删除dialog
  const [isConfirmDeleteOpen, setIsConfirmDeleteOpen] = useState(false);
  const [deleteFunction, setDeleteFunction] = useState<(() => void) | null>(
    null
  );
  const [deleteMessage, setDeleteMessage] = useState<string>('');

  // 添加新的状态变量
  const [title, setTitle] = useState(demoReport.title);
  const [description, setDescription] = useState(demoReport.description);

  // todo: 发起api， 保存报表
  useEffect(() => {
    console.log('正在保存 demoReport');
    console.log('layout', layout);
    console.log('dataSources', dataSources);
    console.log('parameters', parameters);
    console.log('artifacts', artifacts);
    console.log('aliasRelianceMap', aliasRelianceMap);
    console.log('title', title);
    console.log('description', description);
    toast.success(`[DEBUG]你保存了报表"${reportId}"`);
  }, [
    layout,
    dataSources,
    parameters,
    artifacts,
    aliasRelianceMap,
    title,
    description,
  ]);

  // 添加图表Artifact: 修改artifacts, layouts
  const handleAddArtifact = (newArtifact: Artifact) => {
    // 添加新的图表
    setArtifacts([...artifacts, newArtifact]);

    // 更新 aliasRelianceMap
    setAliasRelianceMap(
      updateAliasRelianceMapByArtifact(null, newArtifact, aliasRelianceMap)
    );

    // 更新布局
    setLayout(addLayoutItem(layout, newArtifact.id, newArtifact.title));
  };

  // 修改图表: 修改artifacts, layouts
  const handleModifyArtifact = (newArtifact: Artifact) => {
    const oldArtifact = artifacts.find(
      (artifact) => artifact.id === newArtifact.id
    );
    if (!oldArtifact) {
      toast.error('图表不存在');
      return;
    }

    // 如果标题变了，同步更新布局
    if (oldArtifact.title !== newArtifact.title) {
      const newLayout = layout.items.map((item) => {
        if (item.id === newArtifact.id) {
          return { ...item, title: newArtifact.title };
        }
        return item;
      });
      setLayout({ ...layout, items: newLayout });
    }

    setAliasRelianceMap(
      updateAliasRelianceMapByArtifact(
        oldArtifact,
        newArtifact,
        aliasRelianceMap
      )
    );

    // 更新artifacts
    setArtifacts(
      artifacts.map((artifact) =>
        artifact.id === newArtifact.id ? newArtifact : artifact
      )
    );
  };

  // 删除图表: 修改artifacts, layouts
  const handleDeleteArtifact = (artifactId: string) => {
    // if (artifacts.length === 1) {
    //   toast.error('至少需要保留一个图表');
    //   return;
    // }
    // 删除图表
    const oldArtifact = artifacts.find(
      (artifact) => artifact.id === artifactId
    );
    if (!oldArtifact) {
      toast.error('图表不存在');
      return;
    }
    // 更新 aliasRelianceMap
    setAliasRelianceMap(
      updateAliasRelianceMapByArtifact(oldArtifact, null, aliasRelianceMap)
    );

    // 更新artifacts
    setArtifacts(artifacts.filter((artifact) => artifact.id !== artifactId));

    // 更新布局，删除对应的 item
    let newLayout = {
      ...layout,
      items: layout.items.filter((item) => item.id !== artifactId), // 过滤掉被删除的 item
    };
    // 删除空行和空列
    newLayout = removeEmptyRowsAndColumns(newLayout);
    setLayout(newLayout);
    toast.success('图表已删除');
  };

  // 函数： 删除之前的确认， 多个tabs共用
  const confirmDelete = (deleteFunction: () => void, message: string) => {
    setIsConfirmDeleteOpen(true);
    setDeleteFunction(() => deleteFunction);
    setDeleteMessage(message);
  };

  const handleAddDataSource = (dataSource: DataSource) => {
    const { newDataSources, newAliasRelianceMap } = addDataSource(
      dataSource,
      dataSources,
      aliasRelianceMap
    );
    setDataSources(newDataSources);
    setAliasRelianceMap(newAliasRelianceMap);
  };

  const handleEditDataSource = (
    oldDataSource: DataSource,
    newDataSource: DataSource
  ) => {
    const { newDataSources, newAliasRelianceMap } = editDataSource(
      oldDataSource,
      newDataSource,
      dataSources,
      aliasRelianceMap
    );

    setDataSources(newDataSources);
    setAliasRelianceMap(newAliasRelianceMap);
  };

  const handleDeleteDataSource = (dataSource: DataSource) => {
    // 判断数据源是否被图表依赖
    if (
      aliasRelianceMap.aliasToArtifacts[dataSource.alias] &&
      aliasRelianceMap.aliasToArtifacts[dataSource.alias].length > 0
    ) {
      const artifactTitles = aliasRelianceMap.aliasToArtifacts[
        dataSource.alias
      ].map((artifact) => `"${artifact.artifactTitle}"`);
      toast.error(
        `数据源${dataSource.name}被图表[${artifactTitles.join(', ')}]依赖，不能删除`
      );
      return;
    }

    const { newDataSources, newAliasRelianceMap } = deleteDataSource(
      dataSource,
      dataSources,
      artifacts
    );
    setDataSources(newDataSources);
    setAliasRelianceMap(newAliasRelianceMap);
  };

  // 添加参数
  const handleAddParameter = (parameter: Parameter): boolean => {
    const existedOtherParam = parameters.find((p) => p.name === parameter.name);
    if (existedOtherParam) {
      toast.error('[PARAM] 异常, 参数名称已存在');
      return false;
    }
    setParameters([...parameters, parameter]);
    return true;
  };

  // 修改参数
  const handleEditParameter = (parameter: Parameter): boolean => {
    const existedOtherParam = parameters.find(
      (p) => p.name === parameter.name && p.id !== parameter.id
    );
    if (existedOtherParam) {
      toast.error('[PARAM] 异常, 参数名称已存在');
      return false;
    }
    setParameters(
      parameters.map((p) => (p.id === parameter.id ? parameter : p))
    );
    return true;
  };

  // 删除参数
  const handleDeleteParameter = (parameter: Parameter) => {
    setParameters(parameters.filter((p) => p.id !== parameter.id));
  };

  // 处理更新基本信息
  const handleUpdateBasicInfo = (newTitle: string, newDescription: string) => {
    setTitle(newTitle);
    setDescription(newDescription);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onClose}>
        <DialogContent className='max-w-[90vw] h-[70vh] flex flex-col'>
          <DialogHeader>
            <DialogTitle>编辑报表</DialogTitle>
          </DialogHeader>

          <Tabs
            value={activeTab}
            onValueChange={setActiveTab}
            className='flex-1 flex flex-col overflow-hidden'
          >
            <TabsList className='w-full grid grid-cols-4 sticky top-0 z-10'>
              <TabsTrigger value='info' className='flex items-center gap-2'>
                <Info size={24} />
                <span>基本信息</span>
              </TabsTrigger>

              <TabsTrigger value='filters' className='flex items-center gap-2'>
                <Filter size={24} />
                <span>筛选条件</span>
              </TabsTrigger>

              <TabsTrigger value='data' className='flex items-center gap-2'>
                <Database size={24} />
                <span>数据源</span>
              </TabsTrigger>

              <TabsTrigger
                value='artifacts'
                className='flex items-center gap-2'
              >
                <BarChart2 size={24} />
                <span>图表</span>
              </TabsTrigger>
            </TabsList>

            <div className='flex-1 overflow-y-auto'>
              {activeTab === 'info' && (
                <TabBasicInfo
                  title={title}
                  description={description}
                  onUpdate={handleUpdateBasicInfo}
                />
              )}

              <TabDataSource
                dataSources={dataSources}
                setDataSources={setDataSources}
                engineChoices={demoDataSourceEngineChoices}
                aliasRelianceMap={aliasRelianceMap}
                handleAddDataSource={handleAddDataSource}
                handleEditDataSource={handleEditDataSource}
                handleDeleteDataSource={handleDeleteDataSource}
                confirmDelete={confirmDelete}
              />
              <TabFilter
                parameters={parameters}
                handleDeleteParameter={handleDeleteParameter}
                handleAddParameter={handleAddParameter}
                handleEditParameter={handleEditParameter}
                confirmDelete={confirmDelete}
              />
              <TabArtifact
                layout={layout}
                setLayout={setLayout}
                handleAddArtifact={handleAddArtifact}
                handleModifyArtifact={handleModifyArtifact}
                handleDeleteArtifact={handleDeleteArtifact}
                confirmDelete={confirmDelete}
                artifacts={artifacts}
                dataSources={dataSources}
                engineChoices={demoArtifactEngineChoices}
              />
            </div>
          </Tabs>
        </DialogContent>
      </Dialog>

      {/* 确认删除对话框, 多个tabs共用 */}
      <Dialog
        open={isConfirmDeleteOpen}
        onOpenChange={() => setIsConfirmDeleteOpen(false)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认</DialogTitle>
          </DialogHeader>
          <p>{deleteMessage}</p>
          <DialogFooter>
            <Button
              variant='outline'
              onClick={() => setIsConfirmDeleteOpen(false)}
            >
              取消
            </Button>
            <Button
              onClick={() => {
                if (deleteFunction) {
                  deleteFunction();
                }
                setIsConfirmDeleteOpen(false);
              }}
            >
              确认
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default EditModal;
