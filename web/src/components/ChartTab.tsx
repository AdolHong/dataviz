import { Button } from "@/components/ui/button";
import { Trash2, Pencil, Plus } from "lucide-react";
import { TabsContent } from "@/components/ui/tabs";
import { type Layout } from "@/types/models/layout";
import { useState } from "react";
import { EditLayoutModal } from "./EditLayoutModal";

const ChartTab = ({
  layout,
  setLayout,
  handleAddChart,
  handleDeleteChart,
  confirmDelete,
}: {
  layout: Layout;
  setLayout: (layout: Layout) => void;
  handleAddChart: () => void;
  handleDeleteChart: (id: string) => void;
  confirmDelete: (deleteFunction: () => void, message: string) => void;
}) => {
  const [isLayoutModalOpen, setIsLayoutModalOpen] = useState(false);

  return (
    <div>
      <TabsContent value="charts" className="p-4">
        <div className="space-y-4">
          <div className="border rounded-lg p-4">
            {layout ? (
              <div
                className="grid gap-4 relative"
                style={{
                  gridTemplateColumns: `repeat(${layout.columns}, 1fr)`,
                  gridTemplateRows: `repeat(${layout.rows}, 100px)`,
                  minHeight: "100px",
                }}
              >
                {layout.items.map((item) => (
                  <div
                    key={item.id}
                    className="border-2 border-dashed rounded-lg p-4 text-center bg-gray-200 flex items-center justify-center relative group"
                    style={{
                      gridColumn: `${item.x + 1} / span ${item.width}`,
                      gridRow: `${item.y + 1} / span ${item.height}`,
                    }}
                  >
                    {item.title}
                    <div className="absolute bottom-0  flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-4 w-4"
                        onClick={() => {
                          /* 编辑逻辑 */
                        }}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-4 w-4 text-destructive"
                        onClick={() =>
                          confirmDelete(
                            () => handleDeleteChart(item.id),
                            `您确定要删除 "${item.title}" 吗？`
                          )
                        }
                      >
                        <Trash2 className="h-4 w-4 text-black" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center p-4">正在加载布局...</div>
            )}
          </div>

          <div className="mt-6">
            <Button
              variant="outline"
              className="w-full border-dashed"
              onClick={handleAddChart}
            >
              <Plus className="h-4 w-4 mr-2" />
              添加图表
            </Button>
            <Button
              variant="outline"
              className="w-full border-dashed mt-2"
              onClick={() => setIsLayoutModalOpen(true)}
            >
              <Plus className="h-4 w-4 mr-2" />
              修改布局
            </Button>
          </div>
        </div>
      </TabsContent>

      <EditLayoutModal
        open={isLayoutModalOpen}
        onClose={() => setIsLayoutModalOpen(false)}
        onSave={(newLayout) => {
          setLayout(newLayout);
          setIsLayoutModalOpen(false);
        }}
        initialLayout={layout}
      />
    </div>
  );
};

export default ChartTab;
