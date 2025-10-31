import React, { useEffect, useRef, useState } from 'react';

// 为自定义元素创建单独的接口，避免与已有的JSX.IntrinsicElements冲突
interface JsxPerspectiveViewerElement {
  ref?: React.RefObject<any>;
  className?: string;
  style?: React.CSSProperties;
  // 其他可能需要的属性
  [key: string]: any;
}

// 声明自定义元素和类型
declare global {
  namespace JSX {
    interface IntrinsicElements {
      'perspective-viewer': JsxPerspectiveViewerElement;
    }
  }
}

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
  const wasmLoaded = useRef<boolean>(false);
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

  // 预加载WASM文件
  useEffect(() => {
    // 只加载一次WASM文件
    if (wasmLoaded.current) return;

    const loadWasmFiles = async () => {
      try {
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
          import perspective from "https://unpkg.com/@finos/perspective@3.8.0/dist/cdn/perspective.js";
          import "https://unpkg.com/@finos/perspective-viewer@3.8.0/dist/cdn/perspective-viewer.js";
          import "https://unpkg.com/@finos/perspective-viewer-datagrid@3.8.0/dist/cdn/perspective-viewer-datagrid.js";
          import "https://unpkg.com/@finos/perspective-viewer-d3fc@3.8.0/dist/cdn/perspective-viewer-d3fc.js";
          
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
          setTimeout(initPerspective, 100);
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
          // 设置默认配置
          await viewerRef.current.restore({
            ...JSON.parse(config),
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
    }, 300); // 延迟1秒确保所有资源加载完成

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

// 为window对象添加perspective属性
declare global {
  interface Window {
    perspective: any;
  }
}
