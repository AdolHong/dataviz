import { createFileRoute } from '@tanstack/react-router';
import { useEffect, useState } from 'react';
import EditModal from '@/components/edit/EditModal';
import { reportApi } from '@/api/report';
import type { Layout } from '@/types';
import type { Artifact } from '@/types';
import type { Parameter } from '@/types';
import { set } from 'date-fns';
import type { DataSource } from '@/types';

export const Route = createFileRoute('/dev/edit')({
  component: Edit,
});

function Edit() {
  const [isModalOpen, setIsModalOpen] = useState(true);
  const [reportId, setReportId] = useState('file-1743428151348');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [parameters, setParameters] = useState<Parameter[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [layout, setLayout] = useState<Layout>({
    items: [],
    columns: 1,
    rows: 1,
  });

  useEffect(() => {
    reportApi.getReportByFileId(reportId).then((report) => {
      setParameters(report.parameters || []);
      setArtifacts(report.artifacts || []);
      setDataSources(report.dataSources || []);
      setLayout(report.layout || []);

      console.log('report', report);
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
    if (isModalOpen) {
      console.log('[DEBUG]isModalOpen', isModalOpen);

      const report = {
        id: reportId,
        title: title,
        description: description,
        parameters,
        artifacts,
        dataSources,
        layout,
      };

      console.log('[DEBUG]report', report);

      reportApi.updateReport(reportId, report).then((res) => {
        console.log('res', res);
      });
    }
  };

  return (
    <EditModal
      open={isModalOpen}
      title={title}
      setTitle={setTitle}
      description={description}
      setDescription={setDescription}
      dataSources={dataSources}
      setDataSources={setDataSources}
      parameters={parameters}
      setParameters={setParameters}
      artifacts={artifacts}
      setArtifacts={setArtifacts}
      layout={layout}
      setLayout={setLayout}
      handleSave={handleSave}
      onClose={() => setIsModalOpen(false)}
      reportId={'临时id'} // todo: 获取报表的id
    />
  );
}
