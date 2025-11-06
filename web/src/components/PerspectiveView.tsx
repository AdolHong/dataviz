import React, { useEffect, useRef, useState } from 'react';
import perspective from '@finos/perspective';
import perspective_viewer from '@finos/perspective-viewer';
import '@finos/perspective-viewer-datagrid';
import '@finos/perspective-viewer-d3fc';
import '@finos/perspective-viewer/dist/css/themes.css';

// 导入 WASM 文件
import SERVER_WASM from '@finos/perspective/dist/wasm/perspective-server.wasm?url';
import CLIENT_WASM from '@finos/perspective-viewer/dist/wasm/perspective-viewer.wasm?url';

// @finos/perspective-viewer 包自带类型定义，无需重复声明

// 全局初始化标志和 Promise，确保 WASM 只初始化一次
let wasmInitialized = false;
let wasmInitPromise: Promise<void> | null = null;
let globalWorker: any = null;

// 全局初始化函数，确保只调用一次
const initPerspectiveWasm = async () => {
  if (wasmInitialized) {
    return globalWorker;
  }

  if (wasmInitPromise) {
    await wasmInitPromise;
    return globalWorker;
  }

  wasmInitPromise = (async () => {
    try {
      // 初始化 WASM 文件
      await Promise.all([
        perspective.init_server(fetch(SERVER_WASM)),
        perspective_viewer.init_client(fetch(CLIENT_WASM)),
      ]);
      
      // 初始化 worker
      globalWorker = await perspective.worker();
      wasmInitialized = true;
    } catch (error) {
      console.error('初始化 Perspective WASM 错误:', error);
      wasmInitPromise = null; // 重置以便重试
      throw error;
    }
  })();

  await wasmInitPromise;
  return globalWorker;
};

// 扩展HTMLElement以包含Perspective方法
interface PerspectiveViewerElement extends HTMLElement {
  load: (table: any) => Promise<void>;
  restore: (config: any) => Promise<void>;
  save: () => Promise<any>;
}

interface PerspectiveViewProps {
  data: string; // JSON string from ArtifactTableDataContext
  config: string; // JSON string from ConfigContext
}

// 添加一个安全的复制函数
const safeCopyToClipboard = async (content: string) => {
  // 检查 Clipboard API 是否可用
  if (
    navigator?.clipboard &&
    navigator?.clipboard?.writeText &&
    typeof navigator?.clipboard?.writeText === 'function'
  ) {
    try {
      await navigator.clipboard.writeText(content);
      return true;
    } catch {
      return false;
    }
  }

  // 备选方案：使用 document.execCommand
  try {
    const textArea = document.createElement('textarea');
    textArea.value = content;
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.select();

    const successful = document.execCommand('copy');
    document.body.removeChild(textArea);
    return successful;
  } catch {
    return false;
  }
};

export const PerspectiveView: React.FC<PerspectiveViewProps> = ({
  data,
  config = '{}',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<PerspectiveViewerElement | null>(null);
  const tableRef = useRef<any>(null);
  const workerRef = useRef<any>(null);
  const [isCopied, setIsCopied] = useState(false);
  const [hasSettings, setHasSettings] = useState(false);

  // 创建perspective-viewer元素
  useEffect(() => {
    if (containerRef.current && !viewerRef.current) {
      // 清空容器
      containerRef.current.innerHTML = '';

      // 创建perspective-viewer元素
      const viewer = document.createElement('perspective-viewer');
      viewer.className = 'absolute inset-0';
      containerRef.current.appendChild(viewer);

      // 保存引用
      viewerRef.current = viewer as PerspectiveViewerElement;
    }

    return () => {
      // 组件卸载时清理
      if (viewerRef.current && viewerRef.current.parentNode) {
        viewerRef.current.parentNode.removeChild(viewerRef.current);
        viewerRef.current = null;
      }
    };
  }, []);

  // 监听 settings 属性变化
  useEffect(() => {
    if (!viewerRef.current) return;

    // 检查初始状态
    setHasSettings(viewerRef.current.hasAttribute('settings'));

    // 创建 MutationObserver 监听属性变化
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (
          mutation.type === 'attributes' &&
          mutation.attributeName === 'settings'
        ) {
          const hasSettingsAttr = viewerRef.current?.hasAttribute('settings');
          setHasSettings(!!hasSettingsAttr);
        }
      });
    });

    // 开始监听
    observer.observe(viewerRef.current, { attributes: true });

    // 清理函数
    return () => {
      observer.disconnect();
    };
  }, [viewerRef.current]);

  // 初始化 Perspective WASM 和 worker（使用全局初始化，确保只初始化一次）
  useEffect(() => {
    const initWorker = async () => {
      if (!workerRef.current) {
        try {
          workerRef.current = await initPerspectiveWasm();
        } catch (error) {
          console.error('获取 Perspective worker 错误:', error);
        }
      }
    };
    initWorker();
  }, []);

  // 解析JSON数据并初始化Perspective
  useEffect(() => {
    let timer: number | undefined;
    let viewInstance: any = null;

    const initPerspective = async () => {
      try {
        // 等待确保 worker 已初始化
        if (!workerRef.current) {
          console.log('等待 Perspective worker 初始化...');
          setTimeout(initPerspective, 100);
          return;
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

          // 获取表的 schema 来识别日期列
          let dateColumns: string[] = [];
          try {
            const schema = await tableRef.current.schema();
            // schema 是一个对象，key 是列名，value 是类型（如 'datetime', 'date'）
            dateColumns = Object.keys(schema).filter(
              (col) => schema[col] === 'datetime' || schema[col] === 'date'
            );
          } catch (error) {
            console.log('获取表结构失败，尝试从数据推断日期列:', error);
            // 如果获取 schema 失败，尝试从数据推断日期列
            if (parsedData.length > 0) {
              const firstRow = parsedData[0];
              dateColumns = Object.keys(firstRow).filter((key) => {
                const value = firstRow[key];
                return value != null && (
                  typeof value === 'string' && !isNaN(Date.parse(value)) ||
                  value instanceof Date
                );
              });
            }
          }

          // 构建列配置，为所有日期列设置默认时区
          const parsedConfig = JSON.parse(config);
          const existingColumnsConfig = parsedConfig.columns_config || {};
          
          // 使用展开运算符构建新的配置对象，避免直接修改原对象
          let columnsConfig = { ...existingColumnsConfig };
          
          // 为每个日期列设置默认时区（如果还没有设置）
          dateColumns.forEach((colName) => {
            const existingColConfig = existingColumnsConfig[colName];
            const existingDateFormat = existingColConfig?.date_format;
            
            // 只在列配置中没有时区时才设置默认时区
            if (!existingDateFormat?.timeZone) {
              console.log('设置默认时区为 Atlantic/Reykjavik', colName);
              columnsConfig = {
                ...columnsConfig,
                [colName]: {
                  ...existingColConfig,
                  date_format: {
                    ...existingDateFormat,
                    timeZone: 'Atlantic/Reykjavik',
                  },
                },
              };
            }
          });

          
          // 设置默认配置
          await viewerRef.current.restore({
            ...parsedConfig,
            columns_config: columnsConfig,
            settings: false,
          });

          // viewerRef.current.
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
    }, 100); // 使用 Bundler 方式，延迟时间可以缩短

    // 组件卸载时清理资源
    return () => {
      // 清除定时器
      if (timer) window.clearTimeout(timer);

      // 安全地清理资源
      const cleanup = async () => {
        try {
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

          // 注意：不清理全局 worker，因为它是共享的，其他组件可能还在使用
          // 只清理本组件的引用
          workerRef.current = null;
        } catch (error) {
          console.log('清理资源时发生错误，可以忽略:', error);
        }
      };

      // 执行清理
      cleanup();
    };
  }, [data]);

  // 复制配置到剪贴板
  const copyConfigToClipboard = async () => {
    if (!viewerRef.current) return;

    try {
      const currentConfig = await viewerRef.current.save();
      console.info('currentConfig', currentConfig);

      const configString = JSON.stringify(currentConfig, null);
      const pastedText = `# 设置用于画图的df
df = None
assert df is not None, "需要设置df，用于画图"

# import
import json

config = json.loads("""${configString}""")
result = (df, config)
`;

      //       const pastedText = `# 设置用于画图的df
      // df = None
      // assert df is not None, "需要设置df，用于画图"

      // # import
      // import json
      // import perspective
      // from perspective.widget import PerspectiveWidget

      // config = json.loads("""${configString}""")
      // table = perspective.table(df)
      // widget = PerspectiveWidget(table, **config)
      // result = widget
      // result
      // `;

      const copySuccess = await safeCopyToClipboard(pastedText);

      if (copySuccess) {
        setIsCopied(true);
        console.log('配置已复制到剪贴板:', configString);

        // 3秒后重置复制状态
        setTimeout(() => {
          setIsCopied(false);
        }, 3000);
      } else {
        console.error('复制到剪贴板失败');
        alert('复制到剪贴板失败，请手动复制');
      }
    } catch (error) {
      console.error('复制配置到剪贴板错误:', error);
    }
  };

  return (
    <div className={`flex flex-col h-full`}>
      <div
        ref={containerRef}
        className={`flex-1 h-full relative   overflow-hidden  ${hasSettings ? 'min-h-[680px]' : 'min-h-[300px]'}`}
      ></div>

      {hasSettings && (
        <div className='flex justify-end mt-3'>
          <button
            className={`px-3 py-1 rounded-md text-sm ${isCopied ? 'bg-blue-500 text-white' : 'bg-gray-400 text-white hover:bg-gray-600'}`}
            onClick={copyConfigToClipboard}
          >
            {isCopied ? '已复制至剪切板！' : '导出画图'}
          </button>
        </div>
      )}
    </div>
  );
};

