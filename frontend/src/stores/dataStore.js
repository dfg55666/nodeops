import { create } from 'zustand';
import * as api from '../api';

const useDataStore = create((set, get) => ({
  projects: [],
  accounts: [],
  tasks: {},       // keyed by projectName → array of tasks
  overview: {},
  loading: false,
  error: null,

  // ─── Fetch helpers ──────────────────────────────────────────────────────────
  fetchProjects: async () => {
    try {
      set({ loading: true });
      const res = await api.getProjects();
      const projects = res.data ?? res ?? [];
      set({ projects: Array.isArray(projects) ? projects : [], loading: false });
    } catch (e) {
      set({ error: e.message, loading: false });
    }
  },

  fetchAccounts: async () => {
    try {
      const res = await api.getAccounts();
      const accounts = res.data ?? res ?? [];
      set({ accounts: Array.isArray(accounts) ? accounts : [] });
    } catch (e) {
      set({ error: e.message });
    }
  },

  fetchTasks: async (projectName) => {
    try {
      const res = await api.getTasksForProject(projectName);
      const tasks = res.data ?? res ?? [];
      set((state) => ({
        tasks: {
          ...state.tasks,
          [projectName]: Array.isArray(tasks) ? tasks : [],
        },
      }));
    } catch (e) {
      set({ error: e.message });
    }
  },

  fetchAllTasks: async () => {
    try {
      const res = await api.getAllTasks();
      const raw = res.data ?? res ?? {};
      if (Array.isArray(raw)) {
        const grouped = {};
        raw.forEach((t) => {
          const p = t.project || 'unknown';
          if (!grouped[p]) grouped[p] = [];
          grouped[p].push(t);
        });
        set({ tasks: grouped });
      } else {
        // Already grouped by project name
        set({ tasks: raw });
      }
    } catch (e) {
      set({ error: e.message });
    }
  },

  fetchOverview: async () => {
    try {
      const res = await api.getOverview();
      set({ overview: res.data ?? res ?? {} });
    } catch (e) {
      console.warn('Overview fetch failed:', e.message);
    }
  },

  // ─── Accounts ────────────────────────────────────────────────────────────────
  addAccount: async (data) => {
    const res = await api.createAccount(data);
    await get().fetchAccounts();
    return res;
  },

  editAccount: async (id, data) => {
    const res = await api.updateAccount(id, data);
    await get().fetchAccounts();
    return res;
  },

  removeAccount: async (id) => {
    await api.deleteAccount(id);
    await get().fetchAccounts();
  },

  unbindAccountTask: async (id) => {
    const res = await api.unbindAccountTask(id);
    await get().fetchAccounts();
    return res;
  },

  refreshAccountCredits: async (id) => {
    const res = await api.refreshCredits(id);
    await get().fetchAccounts();
    return res;
  },

  // ─── Projects ─────────────────────────────────────────────────────────────────
  addProject: async (data) => {
    const res = await api.createProject(data);
    await get().fetchProjects();
    return res;
  },

  removeProject: async (name) => {
    await api.deleteProject(name);
    set((state) => {
      const tasks = { ...state.tasks };
      delete tasks[name];
      return {
        projects: state.projects.filter((p) => (p.name || p) !== name),
        tasks,
      };
    });
  },

  // ─── Tasks ────────────────────────────────────────────────────────────────────
  createTask: async (data) => {
    const res = await api.createTask(data);
    await get().fetchTasks(data.project);
    return res;
  },

  startTask: async (project, taskId) => {
    const res = await api.startTask(project, taskId);
    await get().fetchTasks(project);
    return res;
  },

  cancelTask: async (project, taskId) => {
    const res = await api.cancelTask(project, taskId);
    await get().fetchTasks(project);
    return res;
  },

  deleteTask: async (project, taskId) => {
    await api.deleteTask(project, taskId);
    set((state) => ({
      tasks: {
        ...state.tasks,
        [project]: (state.tasks[project] || []).filter(
          (t) => t.id !== taskId && t.task_id !== taskId
        ),
      },
    }));
  },

  clearError: () => set({ error: null }),
}));

export default useDataStore;
