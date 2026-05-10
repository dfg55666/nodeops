import React, { useState, useEffect, useCallback } from 'react';
import { X, AlertTriangle, CheckCircle, Info } from 'lucide-react';

// ─── Singleton event bus ──────────────────────────────────────────────────────
const listeners = new Set();
let nextId = 1;

export function showToast(message, type = 'error') {
  const id = nextId++;
  listeners.forEach((fn) => fn({ id, message, type }));
}

// ─── Toast container (mount once in App) ─────────────────────────────────────
export default function Toast() {
  const [toasts, setToasts] = useState([]);

  const remove = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useEffect(() => {
    const handler = (toast) => {
      setToasts((prev) => [...prev, toast]);
      setTimeout(() => remove(toast.id), 4500);
    };
    listeners.add(handler);
    return () => listeners.delete(handler);
  }, [remove]);

  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 16,
        right: 16,
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        pointerEvents: 'none',
      }}
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onRemove={remove} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onRemove }) {
  const configs = {
    error:   { icon: <AlertTriangle size={13} style={{ color: '#ff6b4a', flexShrink: 0 }} />, border: 'rgba(255,107,74,0.35)', accent: '#ff6b4a' },
    success: { icon: <CheckCircle   size={13} style={{ color: '#00a888', flexShrink: 0 }} />, border: 'rgba(0,168,136,0.35)',  accent: '#00a888' },
    info:    { icon: <Info          size={13} style={{ color: '#4a9eff', flexShrink: 0 }} />, border: 'rgba(74,158,255,0.35)', accent: '#4a9eff' },
  };
  const cfg = configs[toast.type] || configs.info;

  return (
    <div
      style={{
        pointerEvents: 'auto',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 8,
        padding: '8px 10px 8px 12px',
        minWidth: 260,
        maxWidth: 380,
        background: '#ffffff',
        border: `1px solid ${cfg.border}`,
        borderLeft: `3px solid ${cfg.accent}`,
        boxShadow: '0 4px 20px rgba(0,0,0,0.12)',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11,
        color: '#0f172a',
        animation: 'fadeSlideIn 0.2s ease-out',
      }}
    >
      {cfg.icon}
      <span style={{ flex: 1, lineHeight: 1.5 }}>{toast.message}</span>
      <button
        onClick={() => onRemove(toast.id)}
        style={{
          marginLeft: 4,
          background: 'none',
          border: 'none',
          color: '#64748b',
          cursor: 'pointer',
          padding: '1px 2px',
          display: 'flex',
          alignItems: 'center',
          flexShrink: 0,
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = '#0f172a')}
        onMouseLeave={(e) => (e.currentTarget.style.color = '#64748b')}
      >
        <X size={11} />
      </button>

      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateX(16px); }
          to   { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}
