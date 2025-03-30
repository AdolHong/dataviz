import { FileSystemItemType } from '@/types/models/fileSystem';
import type { FileSystemItem } from '@/types/models/fileSystem';

// 演示用文件系统数据
export const demoFileSystemData: FileSystemItem[] = [
  // 根文件夹
  {
    id: 'folder-1',
    name: '销售报表',
    type: FileSystemItemType.FOLDER,
    parentId: null,
    createdAt: '2023-01-01T00:00:00Z',
    updatedAt: '2023-01-01T00:00:00Z',
  },
  {
    id: 'folder-2',
    name: '运营报表',
    type: FileSystemItemType.FOLDER,
    parentId: null,
    createdAt: '2023-01-02T00:00:00Z',
    updatedAt: '2023-01-02T00:00:00Z',
  },
  {
    id: 'folder-3',
    name: '财务报表',
    type: FileSystemItemType.FOLDER,
    parentId: null,
    createdAt: '2023-01-03T00:00:00Z',
    updatedAt: '2023-01-03T00:00:00Z',
  },

  // 销售报表子文件夹
  {
    id: 'folder-11',
    name: '区域销售',
    type: FileSystemItemType.FOLDER,
    parentId: 'folder-1',
    createdAt: '2023-01-10T00:00:00Z',
    updatedAt: '2023-01-10T00:00:00Z',
  },
  {
    id: 'folder-12',
    name: '产品销售',
    type: FileSystemItemType.FOLDER,
    parentId: 'folder-1',
    createdAt: '2023-01-11T00:00:00Z',
    updatedAt: '2023-01-11T00:00:00Z',
  },

  // 销售报表文件
  {
    id: 'file-101',
    name: '总销售概览',
    type: FileSystemItemType.FILE,
    parentId: 'folder-1',
    reportId: 'report-101',
    createdAt: '2023-02-01T00:00:00Z',
    updatedAt: '2023-02-01T00:00:00Z',
  },

  // 区域销售子文件
  {
    id: 'file-111',
    name: '华东区销售报表',
    type: FileSystemItemType.FILE,
    parentId: 'folder-11',
    reportId: 'report-111',
    createdAt: '2023-02-10T00:00:00Z',
    updatedAt: '2023-02-10T00:00:00Z',
  },
  {
    id: 'file-112',
    name: '华南区销售报表',
    type: FileSystemItemType.FILE,
    parentId: 'folder-11',
    reportId: 'report-112',
    createdAt: '2023-02-11T00:00:00Z',
    updatedAt: '2023-02-11T00:00:00Z',
  },
  {
    id: 'file-113',
    name: '华北区销售报表',
    type: FileSystemItemType.FILE,
    parentId: 'folder-11',
    reportId: 'report-113',
    createdAt: '2023-02-12T00:00:00Z',
    updatedAt: '2023-02-12T00:00:00Z',
  },

  // 产品销售子文件
  {
    id: 'file-121',
    name: '电子产品销售报表',
    type: FileSystemItemType.FILE,
    parentId: 'folder-12',
    reportId: 'report-121',
    createdAt: '2023-02-20T00:00:00Z',
    updatedAt: '2023-02-20T00:00:00Z',
  },
  {
    id: 'file-122',
    name: '服装销售报表',
    type: FileSystemItemType.FILE,
    parentId: 'folder-12',
    reportId: 'report-122',
    createdAt: '2023-02-21T00:00:00Z',
    updatedAt: '2023-02-21T00:00:00Z',
  },

  // 运营报表子文件夹
  {
    id: 'folder-21',
    name: '用户运营',
    type: FileSystemItemType.FOLDER,
    parentId: 'folder-2',
    createdAt: '2023-01-20T00:00:00Z',
    updatedAt: '2023-01-20T00:00:00Z',
  },

  // 运营报表文件
  {
    id: 'file-201',
    name: '月度运营概览',
    type: FileSystemItemType.FILE,
    parentId: 'folder-2',
    reportId: 'report-201',
    createdAt: '2023-03-01T00:00:00Z',
    updatedAt: '2023-03-01T00:00:00Z',
  },
  {
    id: 'file-202',
    name: '季度运营报告',
    type: FileSystemItemType.FILE,
    parentId: 'folder-2',
    reportId: 'report-202',
    createdAt: '2023-03-02T00:00:00Z',
    updatedAt: '2023-03-02T00:00:00Z',
  },

  // 用户运营子文件
  {
    id: 'file-211',
    name: '新用户分析',
    type: FileSystemItemType.FILE,
    parentId: 'folder-21',
    reportId: 'report-211',
    createdAt: '2023-03-10T00:00:00Z',
    updatedAt: '2023-03-10T00:00:00Z',
  },
  {
    id: 'file-212',
    name: '用户留存分析',
    type: FileSystemItemType.FILE,
    parentId: 'folder-21',
    reportId: 'report-212',
    createdAt: '2023-03-11T00:00:00Z',
    updatedAt: '2023-03-11T00:00:00Z',
  },

  // 财务报表文件
  {
    id: 'file-301',
    name: '收入报表',
    type: FileSystemItemType.FILE,
    parentId: 'folder-3',
    reportId: 'report-301',
    createdAt: '2023-04-01T00:00:00Z',
    updatedAt: '2023-04-01T00:00:00Z',
  },
  {
    id: 'file-302',
    name: '支出报表',
    type: FileSystemItemType.FILE,
    parentId: 'folder-3',
    reportId: 'report-302',
    createdAt: '2023-04-02T00:00:00Z',
    updatedAt: '2023-04-02T00:00:00Z',
  },
  {
    id: 'file-303',
    name: '利润分析',
    type: FileSystemItemType.FILE,
    parentId: 'folder-3',
    reportId: 'report-303',
    createdAt: '2023-04-03T00:00:00Z',
    updatedAt: '2023-04-03T00:00:00Z',
  },
];
