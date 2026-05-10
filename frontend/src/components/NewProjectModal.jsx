import React, { useState } from 'react';
import { X, GitBranch, Layers, Plus } from 'lucide-react';
import useAppStore from '../stores/appStore';
import useDataStore from '../stores/dataStore';
import { showToast } from './Toast';

export default function NewProjectModal() {
  const { setModal } = useAppStore();
  const { addProject } = useDataStore();

  const [name,      setName]      = useState('');
  const [githubUrl, setGithubUrl] = useState('');
  const [localRepoPath, setLocalRepoPath] = useState('');
  const [desc,      setDesc]      = useState('');
  const [loading,   setLoading]   = useState(false);
  const [errors,    setErrors]    = useState({});

  const validate = () => {
    const e = {};
    if (!name.trim())                         e.name = 'Project name is required';
    else if (!/^[a-z0-9_-]+$/i.test(name))   e.name = 'Only letters, numbers, hyphens, underscores';
    return e;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    try {
      setLoading(true);
      setErrors({});
      await addProject({
        name:       name.trim(),
        github_url: githubUrl.trim() || undefined,
        local_repo_path: localRepoPath.trim() || undefined,
        description: desc.trim()    || undefined,
      });
      showToast(`Project "${name}" created`, 'success');
      setModal(null);
    } catch (err) {
      showToast(`Create failed: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 backdrop-blur-[2px]"
      onClick={(e) => { if (e.target === e.currentTarget) setModal(null); }}
    >
      <div className="relative w-full max-w-md bg-white border border-slate-200 rounded-xl shadow-2xl animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <Layers size={14} className="text-emerald-600" />
            <span className="font-mono font-semibold text-sm text-[#0f172a]">New Project</span>
          </div>
          <button
            onClick={() => setModal(null)}
            className="text-slate-500 hover:text-slate-900 transition-colors p-1"
          >
            <X size={15} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-5 py-4 flex flex-col gap-4">
          {/* Name */}
          <div>
            <label className="block font-mono text-[10px] text-[#64748b] uppercase tracking-widest mb-1.5">
              project name *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my-project"
              autoFocus
              className={`
                w-full bg-white border text-[12px] font-mono text-[#1e293b] rounded-lg
                px-3 py-2 focus:outline-none placeholder-[#94a3b8] transition-colors
                ${errors.name ? 'border-red-300' : 'border-slate-300 focus:border-emerald-400'}
              `}
            />
            {errors.name && (
              <p className="mt-1 font-mono text-[10px] text-red-600">{errors.name}</p>
            )}
          </div>

          {/* GitHub URL */}
          <div>
            <label className="block font-mono text-[10px] text-[#64748b] uppercase tracking-widest mb-1.5">
              github url
            </label>
            <div className="flex items-center border border-slate-300 rounded-lg focus-within:border-emerald-400 bg-white transition-colors">
              <span className="px-2 text-slate-500">
                <GitBranch size={12} />
              </span>
              <input
                type="url"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                placeholder="https://github.com/user/repo"
                className="flex-1 bg-transparent text-[12px] font-mono text-[#334155] py-2 pr-3 focus:outline-none placeholder-[#94a3b8]"
              />
            </div>
          </div>

          {/* Local Repo Path */}
          <div>
            <label className="block font-mono text-[10px] text-[#64748b] uppercase tracking-widest mb-1.5">
              local repo path
            </label>
            <input
              type="text"
              value={localRepoPath}
              onChange={(e) => setLocalRepoPath(e.target.value)}
              placeholder="E:\\project\\my-repo"
              className="w-full bg-white border border-slate-300 rounded-lg focus:border-emerald-400 text-[12px] font-mono text-[#334155] px-3 py-2 focus:outline-none placeholder-[#94a3b8] transition-colors"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block font-mono text-[10px] text-[#64748b] uppercase tracking-widest mb-1.5">
              description
            </label>
            <textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              rows={3}
              placeholder="What does this project do?"
              className="w-full bg-white border border-slate-300 rounded-lg focus:border-emerald-400 text-[12px] font-mono text-[#334155] px-3 py-2 resize-none focus:outline-none placeholder-[#94a3b8] transition-colors"
            />
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            <button
              type="submit"
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-emerald-50 border border-emerald-300 text-emerald-700 font-mono text-[12px] hover:bg-emerald-100 transition-colors disabled:opacity-40"
            >
              <Plus size={12} />
              {loading ? 'Creating…' : 'Create Project'}
            </button>
            <button
              type="button"
              onClick={() => setModal(null)}
              className="px-4 py-2 rounded-lg border border-slate-300 text-slate-600 font-mono text-[12px] hover:bg-slate-50 hover:text-slate-800 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
