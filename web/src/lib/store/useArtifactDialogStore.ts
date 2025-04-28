// 使用Zustand创建store (artifactDialogStore.ts)
import { create } from 'zustand';
import type { Artifact } from '@/types/models/artifact';
import type { ArtifactResponse } from '@/types/api/aritifactRequest';

interface ArtifactDialogState {
  isOpen: boolean;
  artifact: Artifact | null;
  artifactResponse: ArtifactResponse | null;
  openDialog: (artifact: Artifact, artifactResponse: ArtifactResponse) => void;
  closeDialog: () => void;
}

export const useArtifactDialogStore = create<ArtifactDialogState>((set) => ({
  isOpen: false,
  artifact: null,
  artifactResponse: null,
  openDialog: (artifact, artifactResponse) =>
    set({
      isOpen: true,
      artifact,
      artifactResponse,
    }),
  closeDialog: () =>
    set({ isOpen: false, artifact: null, artifactResponse: null }),
}));
