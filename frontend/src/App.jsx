import React, { useEffect, useRef } from 'react';
import useAppStore from './stores/appStore';
import useDataStore from './stores/dataStore';

import Sidebar         from './components/Sidebar';
import StatusBar       from './components/StatusBar';
import ProjectView     from './components/ProjectView';
import TaskView        from './components/TaskView';
import SessionView     from './components/SessionView';
import AccountModal    from './components/AccountModal';
import NewProjectModal from './components/NewProjectModal';
import NewTaskModal    from './components/NewTaskModal';
import Toast           from './components/Toast';

// ─── Loading bar ──────────────────────────────────────────────────────────────
function LoadingBar({ visible }) {
  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: '2px',
        background: 'rgba(0,168,136,0.1)',
        overflow: 'hidden',
        opacity: visible ? 1 : 0,
        transition: 'opacity 0.3s',
        pointerEvents: 'none',
        zIndex: 10,
      }}
    >
      <div
        style={{
          height: '100%',
          background: 'linear-gradient(90deg, transparent, #00a888, transparent)',
          width: '40%',
          animation: visible ? 'loadingSlide 1.2s ease-in-out infinite' : 'none',
        }}
      />
    </div>
  );
}

// ─── Welcome panel ────────────────────────────────────────────────────────────
function WelcomePanel() {
  const { setModal } = useAppStore();

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        gap: '32px',
        userSelect: 'none',
        padding: '24px',
      }}
    >
      {/* ASCII-style logo */}
      <div
        style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: '11px',
          color: '#cbd5e1',
          lineHeight: 1.4,
          textAlign: 'center',
          letterSpacing: '0.05em',
        }}
      >
        {`╔═══════════════════╗\n║   NODEOPS MANAGER  ║\n╚═══════════════════╝`}
      </div>

      <div style={{ textAlign: 'center', maxWidth: 360 }}>
        <h2
          style={{
            fontFamily: 'JetBrains Mono, monospace',
            color: '#334155',
            fontSize: '15px',
            fontWeight: 600,
            margin: '0 0 8px',
            letterSpacing: '0.05em',
          }}
        >
          Multi-account task orchestration
        </h2>
        <p
          style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: '11px',
            color: '#64748b',
            margin: 0,
            lineHeight: 1.7,
          }}
        >
          Manage NodeOps accounts, schedule AI tasks across accounts,
          auto-switch when credits are exhausted.
        </p>
      </div>

      {/* Quick-start grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', width: '100%', maxWidth: 360 }}>
        <QuickBtn
          label="+ New Project"
          desc="Create a project"
          accent
          onClick={() => setModal('newProject')}
        />
        <QuickBtn
          label="Manage Accounts"
          desc="Add / edit accounts"
          onClick={() => setModal('account')}
        />
      </div>

      <div
        style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: '10px',
          color: '#e2e8f0',
          textAlign: 'center',
          lineHeight: 1.8,
        }}
      >
        {'// select a project, task, or session from the sidebar'}
      </div>
    </div>
  );
}

function QuickBtn({ label, desc, accent, onClick }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: 4,
        padding: '12px 14px',
        border: `1px solid ${hover
          ? (accent ? 'rgba(0,168,136,0.5)' : '#94a3b8')
          : (accent ? 'rgba(0,168,136,0.25)' : '#cbd5e1')}`,
        background: hover
          ? (accent ? 'rgba(0,168,136,0.08)' : '#f1f5f9')
          : (accent ? 'rgba(0,168,136,0.04)' : 'transparent'),
        color: accent ? '#00a888' : '#4b5563',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: '11px',
        fontWeight: 500,
        cursor: 'pointer',
        transition: 'all 0.15s',
        textAlign: 'left',
      }}
    >
      <span style={{ color: accent ? '#00a888' : '#475569' }}>{label}</span>
      <span style={{ fontSize: '10px', color: '#64748b', fontWeight: 400 }}>{desc}</span>
    </button>
  );
}

// ─── Content area ─────────────────────────────────────────────────────────────
function ContentArea() {
  const { selectedNode } = useAppStore();
  const { loading } = useDataStore();

  const renderPanel = () => {
    if (!selectedNode) return <WelcomePanel />;
    switch (selectedNode.type) {
      case 'project': return <ProjectView />;
      case 'task':    return <TaskView />;
      case 'session': return <SessionView />;
      default:        return <WelcomePanel />;
    }
  };

  return (
    <div
      style={{
        flex: 1,
        position: 'relative',
        overflow: 'hidden',
        background: '#f8fafc',
      }}
    >
      <LoadingBar visible={loading} />
      <div style={{ height: '100%', overflowY: 'auto' }}>
        {renderPanel()}
      </div>
    </div>
  );
}

// ─── App root ─────────────────────────────────────────────────────────────────
export default function App() {
  const { modalOpen } = useAppStore();
  const { fetchProjects, fetchAccounts, fetchOverview, fetchTasks, tasks } = useDataStore();
  const pollerRef = useRef(null);

  // Initial data load
  useEffect(() => {
    fetchProjects();
    fetchAccounts();
    fetchOverview();
  }, []);

  // Auto-refresh running tasks every 8 s
  useEffect(() => {
    const poll = () => {
      const projectNames = Object.keys(tasks);
      projectNames.forEach((pName) => {
        const taskList = tasks[pName] || [];
        const hasActive = taskList.some((t) =>
          [
            'running', 'pending', 'monitoring', 'switching', 'syncing', 'pushing',
            'acquiring_account', 'auto_registering_account',
            'bootstrapping_runtime', 'creating_session', 'sending_message',
          ].includes(t.status)
        );
        if (hasActive) fetchTasks(pName);
      });
      fetchOverview();
    };
    pollerRef.current = setInterval(poll, 8000);
    return () => clearInterval(pollerRef.current);
  }, [tasks]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        fontFamily: 'Inter, sans-serif',
        color: '#0f172a',
        height: '100vh',
        background: '#f8fafc',
        overflow: 'hidden',
      }}
    >
      <Toast />

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar />
        <ContentArea />
      </div>

      <StatusBar />

      {modalOpen === 'account'    && <AccountModal />}
      {modalOpen === 'newProject' && <NewProjectModal />}
      {modalOpen === 'newTask'    && <NewTaskModal />}

      <style>{`
        @keyframes loadingSlide {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(350%); }
        }
      `}</style>
    </div>
  );
}
