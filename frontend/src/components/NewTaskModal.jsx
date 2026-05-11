import React, { useState } from 'react';
import { X, Play, Terminal, ChevronDown } from 'lucide-react';
import useAppStore from '../stores/appStore';
import useDataStore from '../stores/dataStore';
import { showToast } from './Toast';
import { MODEL_OPTIONS, DEFAULT_MODEL_ID, buildModelRef } from '../constants/models';

const MODES = [
  { value: 'auto',    label: 'auto',    desc: 'Runs multiple loops automatically' },
  { value: 'oneshot', label: 'oneshot', desc: 'Executes a single loop then stops' },
];

export default function NewTaskModal() {
  const { setModal, selectedNode } = useAppStore();
  const { projects, createTask, startTask } = useDataStore();

  // Derive project from currently selected node
  const defaultProject = selectedNode?.project || (projects[0]?.name || projects[0] || '');

  const [project,  setProject]  = useState(defaultProject);
  const [mode,     setMode]     = useState('auto');
  const [taskId,   setTaskId]   = useState('');
  const [maxLoops, setMaxLoops] = useState(5);
  const [message,  setMessage]  = useState('');
  const [commitPrompt, setCommitPrompt] = useState('');
  const [fallbackSync, setFallbackSync] = useState(true);
  const [modelId,  setModelId]  = useState(DEFAULT_MODEL_ID);
  const [autoStart, setAutoStart] = useState(true);
  const [loading,  setLoading]  = useState(false);
  const [errors,   setErrors]   = useState({});

  const validate = () => {
    const e = {};
    if (!project.trim())  e.project = 'Select a project';
    if (!message.trim())  e.message = 'Message / prompt is required';
    if (mode === 'auto' && (maxLoops < 1 || maxLoops > 100))
      e.maxLoops = 'Must be between 1 and 100';
    const tid = taskId.trim();
    if (tid && !/^[a-zA-Z0-9_-]{1,64}$/.test(tid)) {
      e.taskId = 'Only letters, numbers, "_" and "-", max 64 chars';
    }
    return e;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }

    try {
      setLoading(true);
      setErrors({});

      const res = await createTask({
        project:   project.trim(),
        mode,
        message:   message.trim(),
        commit_prompt: commitPrompt.trim() || undefined,
        fallback_sync: Boolean(fallbackSync),
        model:     buildModelRef(modelId) || undefined,
        max_loops: mode === 'auto' ? Number(maxLoops) : 1,
        task_id:   taskId.trim() || undefined,
      });

      const createdTaskId = res?.data?.task_id || res?.task_id || res?.data?.id || res?.id;

      if (autoStart && createdTaskId) {
        try {
          await startTask(project, createdTaskId);
          showToast(`Task created & started`, 'success');
        } catch (startErr) {
          showToast(`Task created but start failed: ${startErr.message}`, 'info');
        }
      } else {
        showToast(`Task created`, 'success');
      }

      setModal(null);
    } catch (err) {
      showToast(`Create failed: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const projectList = projects.map((p) => p.name || p);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 backdrop-blur-[2px]"
      onClick={(e) => { if (e.target === e.currentTarget) setModal(null); }}
    >
      <div
        className="relative w-full max-w-lg bg-white border border-slate-200 rounded-xl shadow-2xl animate-fade-in flex flex-col"
        style={{ maxHeight: '90vh' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Terminal size={14} className="text-emerald-600" />
            <span className="font-mono font-semibold text-sm text-[#0f172a]">New Task</span>
          </div>
          <button
            onClick={() => setModal(null)}
            className="text-slate-500 hover:text-slate-900 transition-colors p-1"
          >
            <X size={15} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-5 py-4 flex flex-col gap-4 overflow-y-auto flex-1">

          {/* Project */}
          <div>
            <label className="block font-mono text-[10px] text-[#64748b] uppercase tracking-widest mb-1.5">
              project *
            </label>
            {projectList.length > 0 ? (
              <div className="relative">
                <select
                  value={project}
                  onChange={(e) => setProject(e.target.value)}
                  className={`
                    w-full appearance-none bg-white border text-[12px] font-mono text-[#1e293b]
                    px-3 py-2 pr-8 focus:outline-none transition-colors rounded-lg
                    ${errors.project ? 'border-red-300' : 'border-slate-300 focus:border-emerald-400'}
                  `}
                >
                  {projectList.map((p) => (
                    <option key={p} value={p} style={{ background: '#ffffff' }}>{p}</option>
                  ))}
                </select>
                <ChevronDown
                  size={12}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#64748b] pointer-events-none"
                />
              </div>
            ) : (
                <input
                  type="text"
                  value={project}
                  onChange={(e) => setProject(e.target.value)}
                  placeholder="project-name"
                  className={`
                  w-full bg-white border text-[12px] font-mono text-[#1e293b]
                  px-3 py-2 focus:outline-none placeholder-[#94a3b8] transition-colors rounded-lg
                  ${errors.project ? 'border-red-300' : 'border-slate-300 focus:border-emerald-400'}
                `}
              />
            )}
            {errors.project && (
              <p className="mt-1 font-mono text-[10px] text-red-600">{errors.project}</p>
            )}
          </div>

          {/* Mode + Max loops */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-mono text-[10px] text-[#64748b] uppercase tracking-widest mb-1.5">
                mode
              </label>
              <div className="flex flex-col gap-1">
                {MODES.map((m) => (
                  <button
                    key={m.value}
                    type="button"
                    onClick={() => setMode(m.value)}
                      className={`
                      flex items-center gap-2 px-3 py-2 text-left border transition-colors
                      font-mono text-[11px] rounded-lg
                      ${mode === m.value
                        ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
                        : 'border-slate-300 bg-white text-[#4b5563] hover:border-slate-400 hover:text-[#334155]'}
                    `}
                  >
                    <span
                      className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                      style={{ background: mode === m.value ? '#00a888' : '#94a3b8' }}
                    />
                    {m.label}
                  </button>
                ))}
              </div>
            </div>

            {mode === 'auto' && (
              <div>
                <label className="block font-mono text-[10px] text-[#64748b] uppercase tracking-widest mb-1.5">
                  max loops
                </label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={maxLoops}
                  onChange={(e) => setMaxLoops(e.target.value)}
                  className={`
                    w-full bg-white border text-[12px] font-mono text-[#1e293b]
                    px-3 py-2 focus:outline-none transition-colors rounded-lg
                    ${errors.maxLoops ? 'border-red-300' : 'border-slate-300 focus:border-emerald-400'}
                  `}
                />
                {errors.maxLoops && (
                  <p className="mt-1 font-mono text-[10px] text-red-600">{errors.maxLoops}</p>
                )}
                <p className="mt-1 font-mono text-[10px] text-[#94a3b8]">
                  {MODES.find((m2) => m2.value === mode)?.desc}
                </p>
              </div>
            )}
          </div>

          {/* Model */}
          <div>
            <label className="block font-mono text-[10px] text-[#64748b] uppercase tracking-widest mb-1.5">
              model
            </label>
            <div className="relative">
              <select
                value={modelId}
                onChange={(e) => setModelId(e.target.value)}
                className="
                  w-full appearance-none bg-white border border-slate-300 text-[12px] font-mono text-[#1e293b]
                  px-3 py-2 pr-8 focus:outline-none focus:border-emerald-400 transition-colors rounded-lg
                "
              >
                {MODEL_OPTIONS.filter((opt) => opt.id).map((opt) => (
                  <option key={opt.id} value={opt.id} style={{ background: '#ffffff' }}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={12}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#64748b] pointer-events-none"
              />
            </div>
            <p className="mt-1 font-mono text-[10px] text-[#94a3b8]">
              provider: openrouter
            </p>
          </div>

          {/* Custom task id */}
          <div>
            <label className="block font-mono text-[10px] text-[#64748b] uppercase tracking-widest mb-1.5">
              task id (optional)
            </label>
            <input
              type="text"
              value={taskId}
              onChange={(e) => setTaskId(e.target.value)}
              placeholder="e.g. task_fix_login_01"
              className={`
                w-full bg-white border text-[12px] font-mono text-[#1e293b]
                px-3 py-2 focus:outline-none placeholder-[#94a3b8] transition-colors rounded-lg
                ${errors.taskId ? 'border-red-300' : 'border-slate-300 focus:border-emerald-400'}
              `}
            />
            {errors.taskId ? (
              <p className="mt-1 font-mono text-[10px] text-red-600">{errors.taskId}</p>
            ) : (
              <p className="mt-1 font-mono text-[10px] text-[#94a3b8]">
                Leave empty to auto-generate.
              </p>
            )}
          </div>

          {/* Message — the main field */}
          <div className="flex-1">
            <label className="block font-mono text-[10px] text-[#64748b] uppercase tracking-widest mb-1.5">
              prompt / message *
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={8}
              placeholder="Describe what you want the agent to do each loop.

Example:
- Check the repository for open issues
- Generate a fix and open a pull request
- Stop when all critical issues are resolved"
              autoFocus
              className={`
                w-full bg-white border text-[12px] font-mono text-[#1e293b]
                px-3 py-2.5 resize-none focus:outline-none placeholder-[#94a3b8] leading-relaxed transition-colors rounded-lg
                ${errors.message ? 'border-red-300' : 'border-slate-300 focus:border-emerald-400'}
              `}
            />
            {errors.message && (
              <p className="mt-1 font-mono text-[10px] text-red-600">{errors.message}</p>
            )}
          </div>

          <div>
            <label className="block font-mono text-[10px] text-[#64748b] uppercase tracking-widest mb-1.5">
              commit prompt (on credit exhausted)
            </label>
            <textarea
              value={commitPrompt}
              onChange={(e) => setCommitPrompt(e.target.value)}
              rows={4}
              placeholder="Ask agent to commit and push in a fresh session on same deployment.

Example:
Please commit all current changes and push to origin. If there are no changes, respond with no-op."
              className="
                w-full bg-white border border-slate-300 text-[12px] font-mono text-[#1e293b]
                px-3 py-2.5 resize-none focus:outline-none focus:border-emerald-400 placeholder-[#94a3b8] leading-relaxed transition-colors rounded-lg
              "
            />
            <p className="mt-1 font-mono text-[10px] text-[#94a3b8]">
              Empty means skip helper push and directly run local fallback sync.
            </p>
          </div>

          {/* Auto-start toggle */}
          <label className="flex items-center gap-2.5 cursor-pointer select-none">
            <div
              onClick={() => setFallbackSync((v) => !v)}
              className={`
                w-8 h-4 relative transition-colors
                ${fallbackSync ? 'bg-emerald-100 border-emerald-300' : 'bg-slate-200 border-slate-300'}
                border rounded-full
              `}
            >
              <span
                className={`
                  absolute top-0.5 w-3 h-3 transition-all rounded-full
                  ${fallbackSync ? 'left-4 bg-emerald-600' : 'left-0.5 bg-[#6b7280]'}
                `}
              />
            </div>
            <span className="font-mono text-[11px] text-[#4b5563]">
              Enable fallback sync when helper push fails
            </span>
          </label>

          {/* Auto-start toggle */}
          <label className="flex items-center gap-2.5 cursor-pointer select-none">
            <div
              onClick={() => setAutoStart((v) => !v)}
              className={`
                w-8 h-4 relative transition-colors
                ${autoStart ? 'bg-emerald-100 border-emerald-300' : 'bg-slate-200 border-slate-300'}
                border rounded-full
              `}
            >
              <span
                className={`
                  absolute top-0.5 w-3 h-3 transition-all rounded-full
                  ${autoStart ? 'left-4 bg-emerald-600' : 'left-0.5 bg-[#6b7280]'}
                `}
              />
            </div>
            <span className="font-mono text-[11px] text-[#4b5563]">
              Start task immediately after creation
            </span>
          </label>

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1 flex-shrink-0">
            <button
              type="submit"
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-emerald-50 border border-emerald-300 text-emerald-700 font-mono text-[12px] hover:bg-emerald-100 transition-colors disabled:opacity-40 rounded-lg"
            >
              <Play size={12} />
              {loading ? 'Creating…' : autoStart ? 'Create & Start' : 'Create Task'}
            </button>
            <button
              type="button"
              onClick={() => setModal(null)}
              className="px-4 py-2.5 border border-slate-300 text-slate-600 font-mono text-[12px] hover:bg-slate-50 hover:text-[#334155] transition-colors rounded-lg"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
