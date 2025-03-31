import { createFileRoute } from '@tanstack/react-router';
import { useEffect, useState } from 'react';
import EditModal from '@/components/edit/EditModal';
import { reportApi } from '@/api/report';
import type { Layout } from '@/types';
import type { Artifact } from '@/types';
import type { Parameter } from '@/types';
import type { DataSource } from '@/types';
import type { Report } from '@/types';

export const Route = createFileRoute('/dev/edit')({
  component: Edit,
});

function Edit({ reportId = 'file-1743436362131' }: { reportId?: string }) {
  const [isModalOpen, setIsModalOpen] = useState(true);
  const [editReport, setEditReport] = useState<Report>();

  useEffect(() => {
    reportApi.getReportByFileId(reportId).then((report) => {
      setEditReport(report);
    });
  }, [reportId]);

  const handleSave = (
    title: string,
    description: string,
    parameters: Parameter[],
    artifacts: Artifact[],
    dataSources: DataSource[],
    layout: Layout
  ) => {
    const report = {
      id: reportId,
      title: title,
      description: description,
      parameters,
      artifacts,
      dataSources,
      layout,
    };

    reportApi.updateReport(reportId, report).then((res) => {
      console.log('res', res);
    });
  };

  return (
    <EditModal
      open={isModalOpen}
      report={editReport as Report}
      handleSave={(
        title,
        description,
        parameters,
        artifacts,
        dataSources,
        layout
      ) => {
        handleSave(
          title,
          description,
          parameters,
          artifacts,
          dataSources,
          layout
        );
        setIsModalOpen(false);
      }}
      onClose={() => setIsModalOpen(false)}
    />
  );
}
