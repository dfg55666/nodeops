# NodeOps Manager — TODO List

> 按依赖顺序排列，前面的完成了后面才能做

---

## Phase 1：后端基础骨架

- [x] 1.1 初始化 FastAPI 项目（main.py, requirements.txt, 目录结构）
- [x] 1.2 文件存储层（file_store.py）— JSON/MD 文件的读写/锁工具
- [x] 1.3 全局配置加载（data/config.json）

## Phase 2：NodeOps API 封装

- [x] 2.1 nodeops_client.py — 认证层（login, verify_otp）
- [x] 2.2 nodeops_client.py — 积分层（get_credits, topup）
- [x] 2.3 nodeops_client.py — 控制面（deployments, usage）
- [x] 2.4 nodeops_client.py — Runtime 层（session, message, file）
- [x] 2.5 SSE 客户端（connect_sse，消息流监听）

## Phase 3：账号与项目管理

- [x] 3.1 账号池（account_pool.py）— 增删改查、选号、锁定、释放
- [x] 3.2 API 路由 accounts.py — 账号 CRUD 接口
- [x] 3.3 项目管理（projects 路由 + git clone）
- [x] 3.4 API 路由 projects.py — 项目 CRUD + 文件树

## Phase 4：任务循环引擎

- [x] 4.1 task_engine.py — 状态机框架（状态流转、持久化）
- [x] 4.2 credit_monitor.py — 额度监控（轮询 + 多信号融合判定）
- [x] 4.3 session_recorder.py — SSE 消息追加写入 .md 文件
- [x] 4.4 workspace_sync.py — 下载 workspace + 文件覆盖 + git push
- [x] 4.5 完整循环流程：额度耗尽 → 同步 → push → 切号 → 新会话 → 发消息
- [x] 4.6 API 路由 tasks.py — 创建/启动/取消/状态查询

## Phase 5：消息与文件代理

- [x] 5.1 API 路由 sessions.py — 查看实时/历史消息
- [x] 5.2 API 路由 files.py — workspace 文件树 + 内容代理
- [x] 5.3 API 路由 events.py — SSE 转发给前端

## Phase 6：Skill API

- [x] 6.1 skills.py — task/create, task/status, task/list, task/cancel
- [x] 6.2 skills.py — project/list, file/tree
- [ ] 6.3 写 Claude Code skill 定义文件

## Phase 7：前端

- [ ] 7.1 初始化 Vite + React 项目，配好代理
- [ ] 7.2 左侧项目树组件（project/task/account/session 树形结构）
- [ ] 7.3 项目概览视图（点 project 显示）
- [ ] 7.4 任务详情视图（状态、循环进度、操作按钮）
- [ ] 7.5 会话消息视图（实时消息流 + 历史记录）
- [ ] 7.6 workspace 文件浏览器（文件树 + 内容预览）
- [ ] 7.7 账号管理弹窗（增删改查、额度显示）
- [ ] 7.8 创建项目/任务表单
- [ ] 7.9 底部状态栏

## Phase 8：联调与完善

- [ ] 8.1 后端所有接口联调 NodeOps 真实 API
- [ ] 8.2 前后端联调
- [ ] 8.3 任务循环完整流程端到端测试
- [ ] 8.4 错误处理与边界情况完善
- [ ] 8.5 start.sh 一键启动脚本
