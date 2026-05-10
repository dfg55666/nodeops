import React, { useEffect, useState } from 'react';
import {
  GitBranch, Plus, ExternalLink, Layers, Clock,
  Play, CheckCircle, AlertCircle, Minus, Circle,
  Trash2, RefreshCw,
} from 'lucide-react';
import useAppStore from '../stores/appStore';
import useDataStore from '../stores/dataStore';
import { showToast } from './Toast';

function statusStyle(status) {
  switch (status) {
    case 'running':
    case 'monitoring':
      return { color: '#00a888', borderColor: 'rgba(0,168,136,0.3)', bg: 'rgba(0,168,136,0.08)' };
    case 'pending':
    case 'switching':
    case 'syncing':
    case 'pushing':
      return { color: '#f59e0b', borderColor: 'rgba(245,158,11,0.3)', bg: 'rgba(245,158,11,0.08)' };
    case 'failed':
    case 'blocked':
    case 'blocked_no_account':
      return { color: '#ff6b4a', borderColor: 'rgba(255,107,74,0.3)', bg: 'rgba(255,107,74,0.08)' };
    case 'completed':
    case 'stopped':
      return { color: '#6b7280', borderColor: 'rgba(107,114,128,0.3)', bg: 'rgba(107,114,128,0.08)' };
    case 'canceled':
      return { color: '#64748b', borderColor: 'rgba(68,68,96,0.3)', bg: 'rgba(68,68,96,0.08)' };
    default:
      return { color: '#6b7280', borderColor: '#cbd5e1', bg: 'transparent' };
  }
}

function StatusIcon({ status }) {
  const sz = 11;
  switch (status) {
    case 'running':
    case 'monitoring':
      return <Play size={sz} style={{ color: '#00a888', flexShrink: 0 }} />;
    case 'pending':
    case 'switching':
    case 'syncing':
    case 'pushing':
      return <Clock size={sz} style={{ color: '#f59e0b', flexShrink: 0 }} />;
    case 'failed':
    case 'blocked':
    case 'blocked_no_account':
      return <AlertCircle size={sz} style={{ color: '#ff6b4a', flexShrink: 0 }} />;
    case 'completed':
    case 'stopped':
      return <CheckCircle size={sz} style={{ color: '#6b7280', flexShrink: 0 }} />;
    case 'canceled':
      return <Minus size={sz} style={{ color: '#64748b', flexShrink: 0 }} />;
    default:
      return <Circle size={sz} style={{ color: '#64748b', flexShrink: 0 }} />;
  }
}

function TaskRow({ task, projectName }) {
  const { setSelectedNode } = useAppStore();
  const [hover, setHover] = useState(false);

  const taskId    = task.id || task.task_id || task.taskId;
  const status    = task.status || 'idle';
  const mode      = task.mode || '—';
  const loops     = task.current_loop ?? task.loop_count ?? 0;
  const maxL      = task.max_loops ?? '∞';
  const st        = statusStyle(status);
  const isActive  = ['running', 'monitoring', 'pending', 'switching', 'syncing', 'pushing'].includes(status);

  return (
    <button
      onClick={() => setSelectedNode({ type: 'task', project: projectName, taskId })}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 12px',
        textAlign: 'left',
        background: hover ? '#f1f5f9' : '#ffffff',
        border: `1px solid ${hover ? '#cbd5e1' : 'transparent'}`,
        cursor: 'pointer',
        transition: 'all 0.15s',
      }}
    >
      <StatusIcon status={status} />

      <span style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 12,
        color: hover ? '#0f172a' : '#1e293b',
        flex: 1,
        minWidth: 0,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
        transition: 'color 0.15s',
      }}>
        {taskId}
      </span>

      {isActive && (
        <span style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: '#00a888',
          boxShadow: '0 0 5px rgba(0,168,136,0.6)',
          animation: 'pulseDot 2s ease-in-out infinite',
          flexShrink: 0,
        }} />
      )}

      <span style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
        padding: '1px 6px',
        border: `1px solid ${st.borderColor}`,
        background: st.bg,
        color: st.color,
        flexShrink: 0,
      }}>
        {status}
      </span>

      <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#64748b', flexShrink: 0 }}>
        {mode}
      </span>

      <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#64748b', flexShrink: 0 }}>
        {loops}/{maxL}
      </span>

      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: hover ? '#6b7280' : '#94a3b8', flexShrink: 0, transition: 'color 0.15s' }}>
        <polyline points="9 18 15 12 9 6" />
      </svg>
    </button>
  );
}

function Stat({ label, value, color }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
      <span style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 18,
        fontWeight: 700,
        color: color || '#0f172a',
      }}>
        {value}
      </span>
      <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#64748b' }}>
        {label}
      </span>
    </div>
  );
}

export default function ProjectView() {
  const { selectedNode, setModal } = useAppStore();
  const { projects, tasks, fetchTasks, removeProject } = useDataStore();
  const [deleting, setDeleting] = useState(false);

  const projectName = selectedNode?.project;
  const project = projects.find((p) => (p.name || p) === projectName) || { name: projectName };
  const taskList = tasks[projectName] || [];

  useEffect(() => {
    if (projectName) fetchTasks(projectName);
  }, [projectName]);

  const runningCount  = taskList.filter((t) => ['running', 'monitoring'].includes(t.status)).length;
  const pendingCount  = taskList.filter((t) => ['pending', 'switching', 'syncing', 'pushing'].includes(t.status)).length;
  const failedCount   = taskList.filter((t) => ['failed', 'blocked', 'blocked_no_account'].includes(t.status)).length;
  const completedCount = taskList.filter((t) => ['completed', 'stopped'].includes(t.status)).length;

  const handleDelete = async () => {
    if (!window.confirm(`Delete project "${projectName}" and all its tasks?`)) return;
    try {
      setDeleting(true);
      await removeProject(projectName);
      showToast(`Project "${projectName}" deleted`, 'success');
    } catch (e) {
      showToast(`Delete failed: ${e.message}`, 'error');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', fontFamily: 'Inter, sans-serif' }}>
      {/* Header */}
      <div style={{
        padding: '20px 24px 16px',
        borderBottom: '1px solid #e2e8f0',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
          {/* Left: icon + name */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
            <div style={{
              flexShrink: 0,
              width: 32,
              height: 32,
              background: '#f1f5f9',
              border: '1px solid #e2e8f0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <Layers size={15} style={{ color: '#00a888' }} />
            </div>
            <div style={{ minWidth: 0 }}>
              <h1 style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontWeight: 700,
                fontSize: 15,
                color: '#0f172a',
                margin: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {project.name}
              </h1>
              {project.github_url && (
                <a
                  href={project.github_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    marginTop: 2,
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: 11,
                    color: 'rgba(74,158,255,0.7)',
                    textDecoration: 'none',
                    transition: 'color 0.15s',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#4a9eff')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = 'rgba(74,158,255,0.7)')}
                >
                  <GitBranch size={10} />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 300 }}>
                    {project.github_url}
                  </span>
                  <ExternalLink size={9} style={{ flexShrink: 0 }} />
                </a>
              )}
            </div>
          </div>

          {/* Right: actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            <button
              onClick={() => setModal('newTask')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 12px',
                background: 'rgba(0,168,136,0.08)',
                border: '1px solid rgba(0,168,136,0.3)',
                color: '#00a888',
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: 11,
                cursor: 'pointer',
                transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(0,168,136,0.15)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(0,168,136,0.08)')}
            >
              <Plus size={11} />
              New Task
            </button>
            <button
              onClick={() => fetchTasks(projectName)}
              title="Refresh tasks"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 28,
                height: 28,
                background: 'none',
                border: '1px solid #cbd5e1',
                color: '#64748b',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.color = '#334155'; e.currentTarget.style.borderColor = '#64748b'; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = '#64748b'; e.currentTarget.style.borderColor = '#cbd5e1'; }}
            >
              <RefreshCw size={12} />
            </button>
            <button
              onClick={handleDelete}
              disabled={deleting}
              title="Delete project"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 28,
                height: 28,
                background: 'none',
                border: '1px solid #cbd5e1',
                color: '#64748b',
                cursor: deleting ? 'not-allowed' : 'pointer',
                opacity: deleting ? 0.5 : 1,
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.color = '#ff6b4a'; e.currentTarget.style.borderColor = 'rgba(255,107,74,0.3)'; e.currentTarget.style.background = 'rgba(255,107,74,0.08)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = '#64748b'; e.currentTarget.style.borderColor = '#cbd5e1'; e.currentTarget.style.background = 'none'; }}
            >
              <Trash2 size={12} />
            </button>
          </div>
        </div>

        {project.description && (
          <p style={{
            marginTop: 12,
            fontSize: 13,
            color: '#4b5563',
            lineHeight: 1.6,
            maxWidth: 600,
          }}>
            {project.description}
          </p>
        )}

        {/* Stats */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 24, marginTop: 14 }}>
          <Stat label="tasks" value={taskList.length} />
          {runningCount > 0  && <Stat label="running"   value={runningCount}   color="#00a888" />}
          {pendingCount > 0  && <Stat label="pending"   value={pendingCount}   color="#f59e0b" />}
          {failedCount > 0   && <Stat label="failed"    value={failedCount}    color="#ff6b4a" />}
          {completedCount > 0 && <Stat label="completed" value={completedCount} color="#6b7280" />}
        </div>
      </div>

      {/* Task list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px' }}>
        {taskList.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 160, gap: 12 }}>
            <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#94a3b8', fontStyle: 'italic', margin: 0 }}>
              No tasks yet.
            </p>
            <button
              onClick={() => setModal('newTask')}
              style={{
                padding: '6px 16px',
                background: 'rgba(0,168,136,0.08)',
                border: '1px solid rgba(0,168,136,0.3)',
                color: '#00a888',
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: 11,
                cursor: 'pointer',
              }}
            >
              Create first task
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                tasks
              </span>
              <div style={{ flex: 1, height: 1, background: '#e2e8f0' }} />
            </div>
            {taskList.map((task, i) => (
              <TaskRow key={task.id || task.task_id || i} task={task} projectName={projectName} />
            ))}
          </div>
        )}
      </div>

      <style>{`
        @keyframes pulseDot { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
      `}</style>
    </div>
  );
}
