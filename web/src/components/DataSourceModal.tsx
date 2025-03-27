import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";

interface DataSourceModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (config: DataSourceConfig) => void;
  initialConfig?: DataSourceConfig;
}

interface DataSourceConfig {
  executorType: string;
  updateMode: string;
  dataFrameName: string;
}

export function DataSourceModal({
  open,
  onClose,
  onSave,
  initialConfig,
}: DataSourceModalProps) {
  const [executorType, setExecutorType] = useState(
    initialConfig?.executorType || ""
  );
  const [updateMode, setUpdateMode] = useState(initialConfig?.updateMode || "");
  const [dataFrameName, setDataFrameName] = useState(
    initialConfig?.dataFrameName || ""
  );

  const handleSave = () => {
    onSave({
      executorType,
      updateMode,
      dataFrameName,
    });
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>数据源配置</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label>执行引擎:</label>
            <Select value={executorType} onValueChange={setExecutorType}>
              <SelectTrigger>
                <SelectValue placeholder="选择执行引擎" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="MySQL">MySQL</SelectItem>
                <SelectItem value="PostgreSQL">PostgreSQL</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <label>更新方式:</label>
            <Select value={updateMode} onValueChange={setUpdateMode}>
              <SelectTrigger>
                <SelectValue placeholder="选择更新方式" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="手动更新">手动更新</SelectItem>
                <SelectItem value="自动更新">自动更新</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <label>DataFrame名称:</label>
            <Input
              value={dataFrameName}
              onChange={(e) => setDataFrameName(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={handleSave}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
