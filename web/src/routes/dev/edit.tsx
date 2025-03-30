import { createFileRoute } from '@tanstack/react-router';
import { useState } from 'react';
import EditModal from '@/pages/edit/EditModal';

export const Route = createFileRoute('/dev/edit')({
  component: Edit,
});

function Edit() {
  const [isModalOpen, setIsModalOpen] = useState(true);

  return (
    <EditModal
      open={isModalOpen}
      onClose={() => setIsModalOpen(false)}
      reportId={'临时id'} // todo: 获取报表的id
    />
  );
}
