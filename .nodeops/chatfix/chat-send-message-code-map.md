# Chat 发送消息代码定位（前端链路）

更新时间：2026-05-10

本文只标注“前端 Chat 发送消息”直接相关代码位置，方便快速排查。

## 1) 前端 UI 层（消息输入与发送）

- 会话页主文件：`frontend/src/components/SessionView.jsx`
  - `SessionComposer` 组件定义：行 `743`
  - 发送函数 `send = async () => { ... }`：行 `799`
  - 调用后端发送接口 `api.sendSessionMessage(...)`：行 `807`
  - 发送模型参数封装 `buildModelRef(modelId)`：行 `812`
  - 模型下拉选择 `modelId` 绑定：行 `1002`

## 2) 前端消息解析与展示（发送后为什么显示成什么样）

- `frontend/src/components/SessionView.jsx`
  - runtime 事件解析 `parseRuntimePayload(...)`：行 `57`
  - 历史会话文本解析 `parseSessionContent(...)`：行 `148`
  - 实时流组件 `LiveMessages`：行 `1072`
  - 拉取任务消息缓存 `api.getTaskMessages(...)`：行 `1122`
  - 订阅 SSE 事件 `api.createTaskEventSource(...)`：行 `1131`

## 3) 前端 API 层（HTTP 调用）

- 文件：`frontend/src/api.js`
  - `sendSessionMessage(sessionId, accountId, data)`：行 `74`
  - `getTaskMessages(project, taskId)`：行 `63`
  - `createTaskEventSource(project, taskId)`：行 `96`

## 4) 模型配置（发送时 model 字段来源）

- 文件：`frontend/src/constants/models.js`
  - 默认模型 `DEFAULT_MODEL_ID`：行 `6`
  - 可选模型列表 `MODEL_OPTIONS`：行 `8`
  - 请求模型对象构造 `buildModelRef(modelId)`：行 `16`

## 5) 后端接收层（前端消息接口落点）

- 文件：`backend/api/sessions.py`
  - 请求模型 `SendMessageRequest`：行 `22`
  - 路由 `POST /api/sessions/{session_id}/message`：行 `65`
  - 路由处理函数 `send_message(...)`：行 `66`
  - 转发 runtime 调用 `noc.send_message(...)`：行 `89`
  - 本地会话文件追加 `_append_local_user_message(...)`：行 `151`, 定义在行 `251`
  - runtime 错误解析 `_extract_runtime_error(...)`：定义在行 `307`

## 6) 后端 runtime 客户端（协议对齐核心）

- 文件：`backend/services/nodeops_client.py`
  - `create_session(...)`：行 `407`
  - `send_message(...)`：行 `449`
  - `noReply` 仅在 `true` 时发送：行 `475`
  - `model` 规范化 `_normalize_model_payload(...)`：定义行 `99`，调用行 `478`
  - token 选择：
    - `/session` 系列创建/列表：`preferred_ygg=project_token`（行 `426`, `442`）
    - `/session/{id}/message|context|subagents` 与 `/file*`：`preferred_ygg=auth_token`（行 `490`, `510`, `530`, `549`, `568`, `607`, `627`, `641`, `666`）

## 7) 上游对照文件（已拷贝到审查目录）

目录：`docs/protocol-review-2026-05-10/`

- 抓包：
  - `network_capture_stop_auto_2026-05-10T03-30-41-407Z.json`
  - `network_capture_stop_auto_2026-05-10T03-30-41-407Z.summary.md`
- 上游 JS（发送与会话逻辑核心）：
  - `1140-a119cc3ed840198c.js`
  - `page-ddfcddf8e457f270.js`
  - `page-b4e39201552430cb.js`

