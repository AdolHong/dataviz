import { Button } from "@/components/ui/button";
import { Trash2, Pencil, Plus } from "lucide-react";
import { type Parameter } from "@/types/models/parameter";
import { TabsContent } from "@radix-ui/react-tabs";

const FilterTab = ({
  parameters,
  handleDeleteParameter,
  confirmDelete,
}: {
  parameters: Parameter[];
  handleDeleteParameter: (id: string) => void;
  confirmDelete: (deleteFunction: () => void, message: string) => void;
}) => {
  return (
    <TabsContent value="filters" className="p-4">
      <div className="space-y-4">
        <div className="space-y-3">
          {parameters.map((parameter) => (
            <div
              key={parameter.name}
              className="border rounded-lg p-4 bg-white shadow-sm"
            >
              <div className="flex justify-between items-center">
                <div>
                  <h4 className="font-medium">{parameter.name}</h4>
                  <p className="text-sm text-gray-500">
                    类型: {parameter.type}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive"
                    onClick={() =>
                      confirmDelete(
                        parameter.name,
                        () => handleDeleteParameter(parameter.name),
                        `您确定要删除参数 ${parameter.name} 吗？`
                      )
                    }
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6">
          <Button
            variant="outline"
            className="w-full border-dashed"
            onClick={() => {}}
          >
            <Plus className="h-4 w-4 mr-2" />
            添加筛选条件
          </Button>
        </div>
      </div>
    </TabsContent>
  );
};

export default FilterTab;
