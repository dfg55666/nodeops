export const MODEL_PROVIDER_OPENROUTER = 'openrouter';

// Captured from NodeOps frontend bundle + send probes:
// - docs/nodeopus-reserve/capture/mcp_chrome_network_capture_createos_nodeops_network_20260216_122120.json
// - docs/nodeopus-reserve/capture/no_credit_send_probe_2026-05-09.json
export const DEFAULT_MODEL_ID = 'anthropic/claude-sonnet-4.6';

export const MODEL_OPTIONS = [
  { id: '', label: 'Use Session Default' },
  { id: 'anthropic/claude-sonnet-4.6', label: 'Claude Sonnet 4.6' },
  { id: 'anthropic/claude-opus-4.7', label: 'Claude Opus 4.7' },
  { id: 'anthropic/claude-opus-4.6', label: 'Claude Opus 4.6' },
  { id: 'openai/gpt-5.4', label: 'GPT-5.4' },
];

export function buildModelRef(modelId) {
  const id = String(modelId || '').trim();
  if (!id) return null;
  return {
    providerID: MODEL_PROVIDER_OPENROUTER,
    modelID: id,
  };
}
