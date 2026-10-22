# 条漫工作台（Comic Workbench）

本地单机的条漫生成管理工作台，集中管理：

1. **启动提示词**：维护每次生成任务使用的全局提示词，支持变量、一键复制、AI 对话优化与恢复默认。
2. **故事管理**：故事名、故事原文、故事封面（图片上传），完整增删改查。
3. **发文管理**：根据故事调用 DeepSeek 生成小红书图文的标题与正文，编辑确认后保存，并跟踪草稿 / 已发布状态。

> 「已发布」目前只是本地状态标记，不会自动调用小红书发布接口。

## 技术栈

- 前端：React 19 + TypeScript + Vite 6 + antd 6.6.7 + @ant-design/x 2.9 + react-router-dom 6
- 后端：Python 3.14 + FastAPI + SQLAlchemy 2（同步）+ SQLite
- 测试：pytest + FastAPI TestClient（DeepSeek 调用全部 mock）

## 快速开始

### 环境要求

- Node.js 18+（本项目锁定 Vite 6，兼容 Node 18）
- [uv](https://docs.astral.sh/uv/)（Python 依赖管理）

### 一键启动（生产模式）

```bash
cd comic-workbench
./start.sh
```

首次运行会自动安装依赖、构建前端，然后访问：

```
http://127.0.0.1:8123
```

### 开发模式（前后端热更新）

```bash
cd comic-workbench
./dev.sh
```

- 前端：http://localhost:5173
- 后端：http://127.0.0.1:8123
- Vite 已将 `/api`、`/uploads` 代理到后端，无需配置 CORS。

## 配置 DeepSeek

有两种方式，**环境变量优先**：

1. 环境变量（推荐）：

   ```bash
   export DEEPSEEK_API_KEY=sk-xxxxxxxx
   ./start.sh
   ```

2. 页面配置：进入「启动提示词」页面，在「DeepSeek 配置」中填写并保存 Key。

说明：

- 页面保存的 Key 以明文存放在本机 SQLite 中（`data/workbench.db`），仅适合本地单机使用。
- 环境变量存在时，页面保存的 Key 不会生效，设置页会显示「环境变量生效」。
- 服务默认只监听 `127.0.0.1`，不要在没有鉴权的情况下改为公网监听。

## 使用流程

1. 在「启动提示词」中按需修改提示词，可使用 `{story_name}`、`{story_content}` 占位符；保存后刷新不会丢失。点击右上角「复制提示词」可一键复制当前内容，粘贴到豆包等外部会话中使用。
   - 点击「AI 优化」可在右侧抽屉中与 AI 对话，说明修改诉求；AI 会基于编辑器中的当前内容流式给出完整新版。
   - 点击 AI 消息下方的「应用到编辑器」，确认无误后再点「保存提示词」；应用本身不会自动保存。
2. 在「故事管理」中新建故事，填写名称与原文，可上传封面（JPG / PNG / WebP，≤5MB）。
3. 在「发文管理」中点击「新建发文」：
   - 选择故事 → 点击「AI 生成文案」；
   - 生成的标题与正文可继续编辑；
   - 选择状态（草稿 / 已发布）后保存。
4. 列表支持按故事、状态、关键词筛选；可编辑、切换发布状态、删除。

## 数据与备份

| 内容 | 路径 |
|---|---|
| 数据库（故事、发文、设置） | `data/workbench.db` |
| 故事封面 | `backend/uploads/` |

备份时复制这两个位置即可。当前未引入数据库迁移工具；若调整表结构，删除 `data/workbench.db` 后重启会重新建表（数据会清空）。

上传封面后若未保存故事，会留下孤儿文件；如有需要可定期清理 `backend/uploads/` 中未被引用的文件。

## 测试

```bash
cd backend
uv run pytest
```

前端类型检查与构建：

```bash
cd frontend
npm run build
```

## 目录结构

```
comic-workbench/
├── backend/
│   ├── app/
│   │   ├── main.py          # 应用工厂、静态资源、异常处理
│   │   ├── routers/         # settings / stories / uploads / posts
│   │   ├── services/        # DeepSeek 调用、文件校验
│   │   ├── models.py        # 数据表
│   │   ├── schemas.py       # 请求/响应模型
│   │   └── crud.py          # 设置读写
│   └── tests/               # pytest 接口测试
├── frontend/
│   └── src/
│       ├── pages/           # 设置 / 故事 / 发文
│       ├── components/      # 封面上传、页面标题、AI 优化抽屉
│       └── api/client.ts    # 统一请求与错误处理
├── data/                    # SQLite（运行时生成）
├── start.sh                 # 生产模式启动
└── dev.sh                   # 开发模式启动
```

## 常见问题

- **生成文案提示「尚未配置 API Key」**：到「启动提示词 → DeepSeek 配置」保存 Key，或设置 `DEEPSEEK_API_KEY` 后重启服务。
- **「AI 优化」按钮不可点击**：该功能复用 DeepSeek Key；按上一条配置后刷新页面即可。
- **DeepSeek 返回 401 / 余额不足**：在设置页更新有效 Key，或检查账户余额。
- **删除故事提示「已有发文记录」**：先删除该故事下的发文，再删除故事（避免误删已发布内容）。
- **端口 8123 被占用**：修改 `start.sh` / `dev.sh` 中的端口，并同步修改 `frontend/vite.config.ts` 的代理地址。
