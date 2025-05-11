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
    let timer: number | undefined;
    let viewInstance: any = null;

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

        // 如果存在旧视图，先关闭
        if (viewInstance) {
          try {
            // 首先尝试卸载视图
            await viewInstance.delete();
          } catch (error) {
            console.log('清理视图失败，可以忽略:', error);
          }
        }

        // 如果存在旧表，先关闭
        if (tableRef.current) {
          try {
            // 安全地尝试删除表
            if (typeof tableRef.current.delete === 'function') {
              await tableRef.current.delete();
            }
          } catch (error) {
            console.log('清理表格失败，可以忽略:', error);
          }
        }

        // 创建新表
        tableRef.current = workerRef.current.table(parsedData);

        // 加载数据到视图
        if (viewerRef.current) {
          await viewerRef.current.load(tableRef.current);
          viewInstance = tableRef.current.view();

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
    timer = window.setTimeout(() => {
      if (viewerRef.current) {
        initPerspective();
      }
    }, 1000); // 延迟1秒确保所有资源加载完成

    // 组件卸载时清理资源
    return () => {
      // 清除定时器
      if (timer) window.clearTimeout(timer);

      // 安全地清理资源
      const cleanup = async () => {
        try {
          // 清理视图实例
          if (viewInstance) {
            try {
              await viewInstance.delete();
            } catch (e) {
              console.log('清理视图实例失败，可以忽略:', e);
            }
          }

          // 清理表格
          if (tableRef.current) {
            try {
              // 安全地检查delete方法是否存在
              if (typeof tableRef.current.delete === 'function') {
                await tableRef.current.delete();
              }
            } catch (e) {
              console.log('清理表格失败，可以忽略:', e);
            }
          }

          // 清理worker
          if (workerRef.current) {
            try {
              if (typeof workerRef.current.terminate === 'function') {
                workerRef.current.terminate();
              }
            } catch (e) {
              console.log('清理worker失败，可以忽略:', e);
            }
          }
        } catch (error) {
          console.log('清理资源时发生错误，可以忽略:', error);
        }
      };

      // 执行清理
      cleanup();
    };
  }, [data]);

  // 导出CSV
  const handleExportCSV = async () => {
    try {
      if (tableRef.current) {
        const view = tableRef.current.view();
        const csv = await view.to_csv();
        view.delete(); // 用完即删
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
        const view = tableRef.current.view();
        const json = await view.to_json();
        view.delete(); // 用完即删
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
    <div className='flex flex-col min-h-[600px]'>
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
