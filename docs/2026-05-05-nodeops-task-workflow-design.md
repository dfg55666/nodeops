# NodeOps Task Workflow Design (V1)

Date: 2026-05-05

## 1. 目标

构建一个以 HTTP 为核心的 NodeOps 执行引擎，提供：

- `task.create` 创建任务并执行消息
- 自动账号管理（优先选已有账号，必要时自动注册）
- 消息拉取（定时 + 手动提前拉取）
- 额度耗尽后的两种策略：自动续跑 / 一次性停止
- 默认后端自动同步并 push 到 GitHub，同时 CLI 也支持手动 push

## 2. 核心决策

1. 接入形态：`HTTP API` 为主。
2. 客户端方式：提供 `CLI` 包装 HTTP（供 skill 调用），不依赖 MCP 注册。
3. `task.create` 入参最小化，仅保留：
   - `mode`: `auto | oneshot`
   - `prompt`: 用户提示词（仓库链接等上下文写在 prompt 内）
4. Git 策略：
   - 默认后端执行同步与 push
   - CLI 额外提供手动 push 能力

## 3. 任务生命周期

建议状态机：

- `pending`
- `running`
- `waiting_pull`（等待下一次定时拉取或手动拉取）
- `blocked_no_credit`（仅 oneshot）
- `syncing_workspace`
- `pushing_github`
- `continuing`（auto 模式切换新账号/新会话后续跑）
- `completed`
- `failed`
- `canceled`

## 4. 工作流程

## 4.1 创建任务

1. 调用 `task.create(mode, prompt)`。
2. 后端创建 task 记录，状态 `pending -> running`。
3. 后端分配账号：
   - 优先可用已注册账号
   - 若无可用账号，触发自动注册
4. 初始化 NodeOps runtime/session，发送首条消息。

## 4.2 消息采集

支持两种方式并存：

1. 自动拉取（默认后台调度）
   - 正常运行阶段可低频（例如 5 分钟）
   - 可按实现调整为“运行中短间隔，空闲后 5 分钟”
2. 手动提前拉取
   - 用户/CLI 主动调用 `task.pull` 立即拉取最新消息

## 4.3 额度耗尽分支

### A. oneshot 模式

- 检测到额度耗尽后：
  - 状态置为 `blocked_no_credit`
  - 不自动续跑
  - 等待人工处理（如手动继续、切换策略）

### B. auto 模式

- 检测到额度耗尽后自动执行：
  1. `syncing_workspace`：拉取云端 workspace 文件
  2. 覆盖本地工作副本
  3. `pushing_github`：提交并 push 到 GitHub（后端默认执行）
  4. 申请新账号或切换可用账号，启动新会话
  5. `continuing`：向新 agent 发送续跑消息（包含 todo 上下文）
  6. 回到 `running`

## 5. HTTP API 草案（V1）

1. `POST /tasks/create`
   - body: `{ "mode": "auto|oneshot", "prompt": "..." }`
   - resp: `{ "task_id": "...", "status": "running" }`

2. `POST /tasks/{task_id}/pull`
   - 作用：立即执行一次消息拉取

3. `GET /tasks/{task_id}`
   - 返回 task 状态、当前账号、会话信息、最近错误

4. `GET /tasks/{task_id}/messages`
   - 支持 cursor 增量读取消息事件

5. `POST /tasks/{task_id}/cancel`
   - 取消任务并停止后续自动动作

6. `POST /tasks/{task_id}/push`（可选）
   - 手动触发一次同步并 push（给 CLI 对应能力）

## 6. CLI 草案（包装 HTTP）

建议命令：

- `nodeops-cli task create --mode auto --prompt "..."`
- `nodeops-cli task pull <task_id>`
- `nodeops-cli task get <task_id>`
- `nodeops-cli task messages <task_id> [--cursor ...]`
- `nodeops-cli task push <task_id>`
- `nodeops-cli task cancel <task_id>`

CLI 不直接实现业务逻辑，只负责请求 HTTP 并展示结果，便于后续 skill 直接调用。

## 7. 同步与 push 策略

- 默认：后端自动 push（auto 模式链路内置）。
- 增补：CLI 提供手动 push，便于人工干预与重试。
- 建议记录每次 push 的 commit id、分支、时间、结果，方便追溯。

## 8. 后续实现注意

本设计文档先聚焦工作流，不锁定 NodeOps 具体底层接口细节；底层端点与字段在开发阶段再做精确对齐与容错实现。

