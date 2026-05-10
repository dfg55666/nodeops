# capture_nodeops_fullchain_chat_20260303_112225 抓包摘要（聊天全链路）

- 文件：`docs/nodeopus-reserve/capture/capture_nodeops_fullchain_chat_20260303_112225.json`
- 时间窗口（UTC）：约 `2026-03-03T11:19` ~ `2026-03-03T11:22`
- 请求总数：`256`
- 终止原因：`user_request`
- 关键域名：
  - `stage-vibe-coder-api.nodeops.xyz`（控制面）
  - `*.syra.nodeops.app`（运行时会话/消息）
  - `api-createos.nodeops.network`（积分与支付）

## 最小聊天闭环（本次实测）

1. `POST /api/v1/deployments`（控制面）
   - 返回：`deployment_id`、`server_endpoint`、`token`（project token）
   - 样例：
     - `id`: `ee853153-aa02-4508-a31a-e00200a72a7b`
     - `server_endpoint`: `https://friendly-jackson4-496776.syra.nodeops.app`

2. `POST {server_endpoint}/session`
   - body: `{"title":"..."}`
   - 返回：`session_id`
   - 样例：`ses_34c92a50dffeltyN28cViEqzkA`

3. `POST {server_endpoint}/session/{session_id}/message`
   - 支持 body 字段：
     - `parts`（text + file）
     - `system`（长系统提示）
     - `model`（`providerID` + `modelID`）
     - `agent`（可选；本次请求未显式传，回包中为 `build`）

4. `GET {server_endpoint}/session/{session_id}/message?_=<ts>` 轮询
   - 返回完整消息数组（user + assistant）
   - 本次末次轮询：`user=3`、`assistant=3`
   - `parts` 类型实测包含：`text`、`step-start`、`step-finish`、`file`

## 消息体字段确认

- 文本消息（示例）

```json
{
  "parts": [{"type": "text", "text": "..."}],
  "system": "...",
  "model": {"providerID": "openrouter", "modelID": "anthropic/claude-opus-4.6"}
}
```

- 带文件消息（示例）

```json
{
  "parts": [
    {"type": "text", "text": "你看得到图片吗"},
    {"type": "file", "mime": "image/png", "url": "data:image/png;base64,..."}
  ],
  "system": "...",
  "model": {"providerID": "openrouter", "modelID": "anthropic/claude-haiku-4.5"}
}
```

## 鉴权头（实测）

- 控制面：`X-Auth-Token`
- 运行时：`x-project-token`

## 重要观察

- 本次 3 次 `POST /session/{id}/message` 中，有 2 次在抓包记录中 `statusCode=null`；
  但随后轮询 `GET /session/{id}/message` 均出现对应 user/assistant 消息，说明请求在服务端已生效。
- 轮询消息中的 `info.model.modelID` 出现：
  - `anthropic/claude-opus-4.6`
  - `anthropic/claude-haiku-4.5`
- 轮询消息中的 `info.agent` 为 `build`（即当前会话 agent mode）。
