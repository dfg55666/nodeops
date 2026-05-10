import React, { useState, useEffect } from 'react';
import {
  FolderOpen, FolderClosed, ChevronRight, ChevronDown,
  Plus, Users, MessageSquare, Play,
  CheckCircle, Clock, AlertCircle, Minus, Circle, Terminal, RefreshCw,
} from 'lucide-react';
import useAppStore from '../stores/appStore';
import useDataStore from '../stores/dataStore';
import * as api from '../api';
import { showToast } from './Toast';

// ─── Status dot ───────────────────────────────────────────────────────────────
function StatusDot({ status, size = 7 }) {
  const map = {
    running:            { color: '#00a888', glow: '0 0 5px rgba(0,168,136,0.8)' },
    monitoring:         { color: '#00a888', glow: '0 0 5px rgba(0,168,136,0.6)' },
    pending:            { color: '#f59e0b', glow: '0 0 4px rgba(245,158,11,0.6)' },
    switching:          { color: '#f59e0b', glow: '0 0 4px rgba(245,158,11,0.5)' },
    syncing:            { color: '#4a9eff', glow: '0 0 4px rgba(74,158,255,0.5)' },
    pushing:            { color: '#4a9eff', glow: '0 0 4px rgba(74,158,255,0.5)' },
    blocked:            { color: '#ff6b4a', glow: '0 0 4px rgba(255,107,74,0.5)' },
    blocked_no_account: { color: '#ff6b4a', glow: '0 0 4px rgba(255,107,74,0.5)' },
    failed:             { color: '#ff6b4a', glow: '0 0 4px rgba(255,107,74,0.5)' },
    completed:          { color: '#6b7280', glow: 'none' },
    stopped:            { color: '#6b7280', glow: 'none' },
    canceled:           { color: '#94a3b8', glow: 'none' },
    idle:               { color: '#94a3b8', glow: 'none' },
  };
  const s = map[status] || map.idle;
  const isActive = ['running', 'monitoring', 'pending', 'switching', 'syncing', 'pushing'].includes(status);
  return (
    <span
      style={{
        display: 'inline-block',
        borderRadius: '50%',
        flexShrink: 0,
        width: size,
        height: size,
        background: s.color,
        boxShadow: s.glow,
        animation: isActive ? 'pulseDot 2s ease-in-out infinite' : 'none',
      }}
    />
  );
}

// ─── Task status icon ─────────────────────────────────────────────────────────
function TaskStatusIcon({ status }) {
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
    case 'blocked':
    case 'blocked_no_account':
    case 'failed':
      return <AlertCircle size={sz} style={{ color: '#ff6b4a', flexShrink: 0 }} />;
    case 'completed':
    case 'stopped':
      return <CheckCircle size={sz} style={{ color: '#6b7280', flexShrink: 0 }} />;
    case 'canceled':
      return <Minus sz={sz} style={{ color: '#64748b', flexShrink: 0 }} />;
    default:
      return <Circle size={sz} style={{ color: '#94a3b8', flexShrink: 0 }} />;
  }
}

// ─── Blinking cursor ──────────────────────────────────────────────────────────
function BlinkCursor() {
  const [on, setOn] = useState(true);
  useEffect(() => {
    const t = setInterval(() => setOn((v) => !v), 600);
    return () => clearInterval(t);
  }, []);
  return (
    <span
      style={{
        display: 'inline-block',
        width: 2,
        height: 13,
        marginLeft: 2,
        background: '#00a888',
        verticalAlign: 'middle',
        opacity: on ? 1 : 0,
        transition: 'opacity 0.1s',
      }}
    />
  );
}

// ─── Session list (lazy-loaded per task expand) ───────────────────────────────
function SessionList({ project, taskId, baseIndent, refreshKey = 0 }) {
  const { selectedNode, setSelectedNode } = useAppStore();
  const [sessions, setSessions] = useState(null);
  const [loading, setLoading]   = useState(false);

  useEffect(() => {
    setLoading(true);
    api.getSessionHistory(project, taskId)
      .then((res) => {
        const data = res.data ?? res;
        setSessions(Array.isArray(data) ? data : []);
      })
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, [project, taskId, refreshKey]);

  const indent = baseIndent;

  if (loading) {
    return (
      <div style={{ paddingLeft: indent, display: 'flex', alignItems: 'center', gap: 5, padding: `3px 0 3px ${indent}px` }}>
        <RefreshCw size={9} style={{ color: '#94a3b8', animation: 'spin 1s linear infinite', flexShrink: 0 }} />
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#94a3b8', fontStyle: 'italic' }}>
          loading…
        </span>
      </div>
    );
  }

  if (!sessions || sessions.length === 0) {
    return (
      <div style={{
        paddingLeft: indent,
        padding: `3px 0 3px ${indent}px`,
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
        color: '#cbd5e1',
        fontStyle: 'italic',
      }}>
        no sessions recorded
      </div>
    );
  }

  return (
    <>
      {sessions.map((s, i) => {
        const accountDir   = s.account_dir || s.account || s.account_email || s.email || '';
        const accountEmail = s.account_email || s.email || s.account || '';
        const sessionFile  = s.session_file || s.file || s.filename || `session-${i + 1}.md`;
        const sessionId    = s.session_id || '';
        const isActive = selectedNode?.type === 'session'
          && selectedNode.project === project
          && selectedNode.taskId === taskId
          && selectedNode.sessionFile === sessionFile;

        return (
          <button
            key={i}
            onClick={() => setSelectedNode({
              type: 'session',
              project,
              taskId,
              accountDir,
              accountEmail,
              sessionFile,
              sessionId,
            })}
            title={sessionFile}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              paddingLeft: indent,
              paddingTop: 3,
              paddingBottom: 3,
              paddingRight: 8,
              textAlign: 'left',
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 10,
              background: isActive ? '#e8f4f1' : 'transparent',
              color: isActive ? '#00a888' : '#4a4a5e',
              border: 'none',
              cursor: 'pointer',
              transition: 'all 0.12s',
            }}
            onMouseEnter={(e) => {
              if (!isActive) {
                e.currentTarget.style.color = '#374151';
                e.currentTarget.style.background = 'rgba(241,245,249,0.4)';
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive) {
                e.currentTarget.style.color = '#4a4a5e';
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            <MessageSquare size={9} style={{ flexShrink: 0, opacity: 0.5 }} />
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {sessionFile.replace(/\.md$/, '')}
            </span>
            {s.status === 'running' && (
              <StatusDot status="running" size={5} />
            )}
          </button>
        );
      })}
    </>
  );
}

// ─── Task row ─────────────────────────────────────────────────────────────────
function TaskRow({ task, project, baseIndent }) {
  const { selectedNode, setSelectedNode } = useAppStore();
  const [open, setOpen] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const [sessionRefreshKey, setSessionRefreshKey] = useState(0);

  const taskId = task.id || task.task_id || task.taskId;
  const status = task.status || 'idle';
  const isActive = selectedNode?.type === 'task'
    && selectedNode.project === project
    && selectedNode.taskId === taskId;
  const isRunning = ['running', 'monitoring', 'pending', 'switching', 'syncing', 'pushing'].includes(status);

  const subIndent = baseIndent + 18;

  const createEmptySession = async (e) => {
    e.stopPropagation();
    if (creatingSession) return;
    try {
      setCreatingSession(true);
      const res = await api.createEmptySessionForTask(project, taskId);
      const data = res.data ?? res ?? {};
      setSessionRefreshKey((v) => v + 1);
      setOpen(true);
      setSelectedNode({
        type: 'session',
        project,
        taskId,
        accountDir: data.account_dir || data.account_email || '',
        accountEmail: data.account_email || data.account_dir || '',
        sessionFile: data.session_file || (data.session_index ? `session-${data.session_index}.md` : ''),
        sessionId: data.session_id || '',
      });
      showToast('Empty session created', 'success');
    } catch (err) {
      showToast(`Create session failed: ${err.message}`, 'error');
    } finally {
      setCreatingSession(false);
    }
  };

  return (
    <>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: isActive ? '#e8f4f1' : 'transparent',
          transition: 'background 0.12s',
        }}
        onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = 'rgba(241,245,249,0.4)'; }}
        onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = 'transparent'; }}
      >
        {/* Expand toggle */}
        <button
          onClick={() => setOpen((v) => !v)}
          style={{
            flexShrink: 0,
            width: 18,
            height: 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginLeft: baseIndent,
            background: 'none',
            border: 'none',
            color: '#94a3b8',
            cursor: 'pointer',
            padding: 0,
          }}
        >
          {open
            ? <ChevronDown size={9} style={{ color: '#6b7280' }} />
            : <ChevronRight size={9} style={{ color: '#94a3b8' }} />}
        </button>

        {/* Task label */}
        <button
          onClick={() => setSelectedNode({ type: 'task', project, taskId })}
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            paddingTop: 3,
            paddingBottom: 3,
            paddingRight: 6,
            textAlign: 'left',
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 11,
            color: isActive ? '#00a888' : '#6a6a88',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            minWidth: 0,
            transition: 'color 0.12s',
          }}
          onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.color = '#1e293b'; }}
          onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.color = '#6a6a88'; }}
        >
          <TaskStatusIcon status={status} />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, fontSize: 11 }}>
            {taskId}
          </span>
          {isRunning && <StatusDot status={status} size={6} />}
        </button>

        <button
          onClick={createEmptySession}
          title={creatingSession ? 'Creating session…' : 'Create empty session'}
          disabled={creatingSession}
          style={{
            flexShrink: 0,
            width: 18,
            height: 18,
            marginRight: 6,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '1px solid rgba(0,168,136,0.25)',
            background: creatingSession ? 'rgba(0,168,136,0.15)' : 'rgba(0,168,136,0.06)',
            color: '#00a888',
            cursor: creatingSession ? 'not-allowed' : 'pointer',
            opacity: creatingSession ? 0.7 : 1,
          }}
        >
          {creatingSession
            ? <RefreshCw size={9} style={{ animation: 'spin 1s linear infinite' }} />
            : <Plus size={9} />}
        </button>
      </div>

      {/* Session subtree */}
      {open && (
        <SessionList
          project={project}
          taskId={taskId}
          baseIndent={subIndent}
          refreshKey={sessionRefreshKey}
        />
      )}
    </>
  );
}

// ─── Project row ─────────────────────────────────────────────────────────────
function ProjectRow({ project }) {
  const { selectedNode, setSelectedNode, setModal } = useAppStore();
  const { tasks, fetchTasks } = useDataStore();
  const [open, setOpen]     = useState(false);
  const [hovered, setHover] = useState(false);

  const name     = project.name || project;
  const isActive = selectedNode?.type === 'project' && selectedNode.project === name;
  const taskList = tasks[name] || [];

  const toggle = () => {
    if (!open) fetchTasks(name);
    setOpen((v) => !v);
  };

  const runningCount = taskList.filter((t) =>
    ['running', 'monitoring'].includes(t.status)
  ).length;
  const pendingCount = taskList.filter((t) =>
    ['pending', 'switching', 'syncing', 'pushing'].includes(t.status)
  ).length;

  return (
    <>
      <div
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        style={{
          display: 'flex',
          alignItems: 'center',
          background: isActive ? '#e8f4f1' : hovered ? 'rgba(241,245,249,0.5)' : 'transparent',
          transition: 'background 0.12s',
        }}
      >
        {/* Chevron */}
        <button
          onClick={toggle}
          style={{
            flexShrink: 0,
            width: 22,
            height: 28,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            paddingLeft: 8,
            background: 'none',
            border: 'none',
            color: '#64748b',
            cursor: 'pointer',
            padding: '0 0 0 8px',
          }}
        >
          {open
            ? <ChevronDown size={10} style={{ color: '#6666aa' }} />
            : <ChevronRight size={10} style={{ color: '#64748b' }} />}
        </button>

        {/* Project name */}
        <button
          onClick={() => setSelectedNode({ type: 'project', project: name })}
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '5px 2px',
            textAlign: 'left',
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 12,
            fontWeight: 600,
            color: isActive ? '#00a888' : hovered ? '#0f172a' : '#475569',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            minWidth: 0,
            transition: 'color 0.12s',
          }}
        >
          {open
            ? <FolderOpen  size={12} style={{ flexShrink: 0, color: isActive ? '#00a888' : 'rgba(0,168,136,0.5)' }} />
            : <FolderClosed size={12} style={{ flexShrink: 0, color: isActive ? '#00a888' : '#6b7280' }} />}
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
            {name}
          </span>

          {/* Running badge */}
          {runningCount > 0 && (
            <span style={{
              fontSize: 9,
              color: '#00a888',
              background: 'rgba(0,168,136,0.12)',
              border: '1px solid rgba(0,168,136,0.3)',
              padding: '0 4px',
              borderRadius: 2,
              flexShrink: 0,
              letterSpacing: '0.05em',
            }}>
              {runningCount}▶
            </span>
          )}
          {runningCount === 0 && pendingCount > 0 && (
            <span style={{
              fontSize: 9,
              color: '#f59e0b',
              background: 'rgba(245,158,11,0.1)',
              border: '1px solid rgba(245,158,11,0.25)',
              padding: '0 4px',
              borderRadius: 2,
              flexShrink: 0,
            }}>
              {pendingCount}⏸
            </span>
          )}
          {runningCount === 0 && pendingCount === 0 && taskList.length > 0 && (
            <span style={{ fontSize: 10, color: '#94a3b8', flexShrink: 0 }}>
              {taskList.length}
            </span>
          )}
        </button>

        {/* Quick new-task button — visible on hover */}
        {hovered && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setSelectedNode({ type: 'project', project: name });
              setModal('newTask');
            }}
            title="New task"
            style={{
              flexShrink: 0,
              width: 20,
              height: 20,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginRight: 4,
              background: 'rgba(0,168,136,0.1)',
              border: '1px solid rgba(0,168,136,0.25)',
              color: '#00a888',
              cursor: 'pointer',
              borderRadius: 2,
              transition: 'all 0.12s',
            }}
          >
            <Plus size={10} />
          </button>
        )}
      </div>

      {/* Task children */}
      {open && (
        taskList.length === 0
          ? (
            <div style={{
              paddingLeft: 36,
              padding: '3px 0 3px 36px',
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 10,
              color: '#cbd5e1',
              fontStyle: 'italic',
            }}>
              no tasks
            </div>
          )
          : taskList.map((task, i) => (
            <TaskRow
              key={task.id || task.task_id || i}
              task={task}
              project={name}
              baseIndent={8}
            />
          ))
      )}
    </>
  );
}

// ─── Main Sidebar ─────────────────────────────────────────────────────────────
export default function Sidebar() {
  const { setModal } = useAppStore();
  const { projects, fetchProjects } = useDataStore();

  return (
    <div
      style={{
        width: 260,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        background: '#f0f4f8',
        borderRight: '1px solid #e8f4f1',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '10px 14px',
          borderBottom: '1px solid #e8f4f1',
          flexShrink: 0,
        }}
      >
        <Terminal size={13} style={{ color: '#00a888' }} />
        <span
          style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontWeight: 700,
            fontSize: 13,
            letterSpacing: '0.15em',
            color: '#00a888',
            textTransform: 'uppercase',
            flex: 1,
          }}
        >
          NodeOps
        </span>
        <BlinkCursor />
        <button
          onClick={fetchProjects}
          title="Refresh"
          style={{
            background: 'none',
            border: 'none',
            color: '#94a3b8',
            cursor: 'pointer',
            padding: 2,
            display: 'flex',
            alignItems: 'center',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = '#00a888')}
          onMouseLeave={(e) => (e.currentTarget.style.color = '#94a3b8')}
        >
          <RefreshCw size={11} />
        </button>
      </div>

      {/* Project tree */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
        {projects.length === 0 ? (
          <div
            style={{
              padding: '20px 16px',
              textAlign: 'center',
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 10,
              color: '#cbd5e1',
              fontStyle: 'italic',
              lineHeight: 1.8,
            }}
          >
            {'no projects\n// create one below'}
          </div>
        ) : (
          projects.map((p, i) => (
            <ProjectRow key={p.name || i} project={p} />
          ))
        )}
      </div>

      {/* Separator */}
      <div style={{ height: 1, background: '#e8f4f1', margin: '0 10px' }} />

      {/* Bottom actions */}
      <div style={{ padding: '6px 10px', display: 'flex', flexDirection: 'column', gap: 1, flexShrink: 0 }}>
        <SidebarAction
          icon={<Plus size={10} />}
          label="New Project"
          onClick={() => setModal('newProject')}
          accent
        />
        <SidebarAction
          icon={<Users size={10} />}
          label="Manage Accounts"
          onClick={() => setModal('account')}
          info
        />
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulseDot { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
      `}</style>
    </div>
  );
}

function SidebarAction({ icon, label, onClick, accent, info }) {
  const [hover, setHover] = useState(false);
  const color = hover
    ? (accent ? '#00a888' : info ? '#4a9eff' : '#334155')
    : '#6b7280';
  const bg = hover
    ? (accent ? 'rgba(0,168,136,0.07)' : info ? 'rgba(74,158,255,0.07)' : '#f1f5f9')
    : 'transparent';

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        padding: '6px 10px',
        width: '100%',
        textAlign: 'left',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11,
        color,
        background: bg,
        border: 'none',
        cursor: 'pointer',
        transition: 'all 0.12s',
        borderRadius: 2,
      }}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}
