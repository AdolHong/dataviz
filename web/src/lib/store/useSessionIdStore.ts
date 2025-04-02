import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { v4 as uuidv4 } from 'uuid';

// 定义 store 的状态类型
interface SessionIdState {
  // 操作方法
  sessionId: string;
  getSessionId: () => string;
}

// 创建 Zustand Store
export const useSessionIdStore = create<SessionIdState>()(
  persist(
    (set, get) => ({
      sessionId: '',
      getSessionId: () => {
        const oldSessionId = get().sessionId;
        const uuid =
          oldSessionId && oldSessionId !== '' ? oldSessionId : uuidv4();
        if (oldSessionId !== uuid) {
          set({ sessionId: uuid });
        }
        return uuid;
      },
    }),
    {
      name: 'sessionid-session-storage', // localStorage 中的 key 名称
      storage: createJSONStorage(() => sessionStorage), // 使用 localStorage 进行存储
      partialize: (state) => ({
        sessionId: state.sessionId,
      }),
    }
  )
);
