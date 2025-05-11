import React, { useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Download } from 'lucide-react';
import { saveAs } from 'file-saver';

// 声明自定义元素和类型
declare global {
  namespace JSX {
    interface IntrinsicElements {
      'perspective-viewer': React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & {
          ref?: React.RefObject<any>;
        },
        HTMLElement
      >;
    }
  }
}

// 扩展HTMLElement以包含Perspective方法
interface PerspectiveViewerElement extends HTMLElement {
  load: (table: any) => Promise<void>;
  restore: (config: any) => Promise<void>;
}

interface PerspectiveTableViewProps {
  data: string; // JSON string from ArtifactTableDataContext
  fileName?: string;
  showExport?: boolean;
}

export const PerspectiveTableView: React.FC<PerspectiveTableViewProps> = ({
  data,
  fileName = 'table-data',
  showExport = true,
}) => {
  const viewerRef = useRef<PerspectiveViewerElement | null>(null);
  const tableRef = useRef<any>(null);
  const workerRef = useRef<any>(null);
  const wasmLoaded = useRef<boolean>(false);

  // 预加载WASM文件
  useEffect(() => {
    // 只加载一次WASM文件
    if (wasmLoaded.current) return;

    const loadWasmFiles = async () => {
      try {
        // 预加载所有必要的WASM文件
        const wasmResources = [
          {
            id: 'perspective-wasm',
            href: 'https://cdn.jsdelivr.net/npm/@finos/perspective/dist/cdn/perspective.wasm',
            type: 'application/wasm',
          },
          {
            id: 'perspective-viewer-wasm',
            href: 'https://cdn.jsdelivr.net/npm/@finos/perspective-viewer/dist/cdn/perspective-viewer.wasm',
            type: 'application/wasm',
          },
        ];

        // 加载CSS
        if (!document.getElementById('perspective-css')) {
          const link = document.createElement('link');
          link.id = 'perspective-css';
          link.rel = 'stylesheet';
          link.type = 'text/css';
          link.href =
            'https://cdn.jsdelivr.net/npm/@finos/perspective-viewer/dist/css/themes.css';
          link.crossOrigin = 'anonymous';
          document.head.appendChild(link);
        }

        // 为每个WASM文件创建预加载链接
        wasmResources.forEach((resource) => {
          if (!document.getElementById(resource.id)) {
            const link = document.createElement('link');
            link.id = resource.id;
            link.rel = 'preload';
            link.href = resource.href;
            link.as = 'fetch';
            link.type = resource.type;
            link.crossOrigin = 'anonymous';
            document.head.appendChild(link);
          }
        });

        wasmLoaded.current = true;
      } catch (error) {
        console.error('加载WASM文件错误:', error);
      }
    };

    // 加载WASM文件
    loadWasmFiles();
  }, []);

  // 加载Perspective插件和模块
  useEffect(() => {
    const loadPerspectiveModules = async () => {
      try {
        // 从CDN动态加载模块
        const perspectiveScript = document.createElement('script');
        perspectiveScript.type = 'module';
        perspectiveScript.innerHTML = `
          import perspective from "https://cdn.jsdelivr.net/npm/@finos/perspective@3.6.0/dist/cdn/perspective.js";
          import "https://cdn.jsdelivr.net/npm/@finos/perspective-viewer@3.6.0/dist/cdn/perspective-viewer.js";
          import "https://cdn.jsdelivr.net/npm/@finos/perspective-viewer-datagrid@3.6.0/dist/cdn/perspective-viewer-datagrid.js";
          import "https://cdn.jsdelivr.net/npm/@finos/perspective-viewer-d3fc@3.6.0/dist/cdn/perspective-viewer-d3fc.js";
          
          window.perspective = perspective;
        `;
        document.head.appendChild(perspectiveScript);
      } catch (error) {
        console.error('加载Perspective模块错误:', error);
      }
    };

    loadPerspectiveModules();
  }, []);

  // 解析JSON数据并初始化Perspective
  useEffect(() => {
    const initPerspective = async () => {
      try {
        // 等待确保WASM和模块已加载
        if (!window.perspective) {
          console.log('等待Perspective初始化...');
          setTimeout(initPerspective, 500);
          return;
        }

        // 初始化worker
        if (!workerRef.current) {
          workerRef.current = await window.perspective.worker();
        }

        // 解析数据
        let parsedData;
        try {
          parsedData = JSON.parse(data);
        } catch (error) {
          console.error('数据解析错误:', error);
          parsedData = [];
        }

        // 如果存在旧表，先关闭
        if (tableRef.current) {
          tableRef.current.delete();
        }

        // 创建新表
        tableRef.current = workerRef.current.table(parsedData);

        // 加载数据到视图
        if (viewerRef.current) {
          await viewerRef.current.load(tableRef.current);

          // 设置默认配置
          await viewerRef.current.restore({
            plugin: 'datagrid',
            settings: true,
            theme: 'material-dark',
          });
        }
      } catch (error) {
        console.error('初始化Perspective错误:', error);
      }
    };

    // 确保DOM已加载
    const timer = setTimeout(() => {
      if (viewerRef.current) {
        initPerspective();
      }
    }, 1000); // 延迟1秒确保所有资源加载完成

    // 组件卸载时清理资源
    return () => {
      clearTimeout(timer);
      if (tableRef.current) {
        tableRef.current.delete();
      }
    };
  }, [data]);

  // 导出CSV
  const handleExportCSV = async () => {
    try {
      if (tableRef.current) {
        const csv = await tableRef.current.view().to_csv();
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        saveAs(blob, `${fileName}.csv`);
      }
    } catch (error) {
      console.error('导出CSV错误:', error);
    }
  };

  // 导出JSON
  const handleExportJSON = async () => {
    try {
      if (tableRef.current) {
        const json = await tableRef.current.view().to_json();
        const blob = new Blob([JSON.stringify(json, null, 2)], {
          type: 'application/json;charset=utf-8;',
        });
        saveAs(blob, `${fileName}.json`);
      }
    } catch (error) {
      console.error('导出JSON错误:', error);
    }
  };

  return (
    <div className='flex flex-col h-full'>
      {showExport && (
        <div className='flex justify-end items-center flex-shrink-0 mb-2'>
          <Button
            variant='outline'
            size='sm'
            onClick={handleExportCSV}
            className='mr-2'
          >
            <Download className='mr-2 h-4 w-4' />
            <span>导出 CSV</span>
          </Button>
          <Button variant='outline' size='sm' onClick={handleExportJSON}>
            <Download className='mr-2 h-4 w-4' />
            <span>导出 JSON</span>
          </Button>
        </div>
      )}

      <div className='flex-grow relative border rounded-md overflow-hidden'>
        <perspective-viewer
          ref={viewerRef as React.RefObject<HTMLElement>}
          className='absolute inset-0'
        />
      </div>
    </div>
  );
};

// 为window对象添加perspective属性
declare global {
  interface Window {
    perspective: any;
  }
}
