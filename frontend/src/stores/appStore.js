import { create } from 'zustand';

// selectedNode shapes:
//   { type: 'project', project: string }
//   { type: 'task',    project: string, taskId: string }
//   { type: 'session', project: string, taskId: string, accountEmail: string, sessionFile: string, sessionId?: string }

const useAppStore = create((set) => ({
  selectedNode: null,
  sidebarOpen: true,
  modalOpen: null, // 'account' | 'newProject' | 'newTask' | null

  setSelectedNode: (node) => set({ selectedNode: node }),
  setSidebarOpen:  (open) => set({ sidebarOpen: open }),
  setModal:        (modal) => set({ modalOpen: modal }),
}));

export default useAppStore;
