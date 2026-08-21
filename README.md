# 企业 RAG + Agent 智能问答平台

前后端分离：`backend/`（FastAPI）+ `frontend/`（Vue 3）+ Docker Compose（PostgreSQL / Redis / Qdrant）。

设计文档：`project-design-doc.md`、`memory-bank/implementation-plan.md`。

---

## 一、你需要先准备什么

| 软件 | 用途 | 说明 |
|------|------|------|
| Docker Desktop | 跑数据库和向量库 | Windows 需启用 WSL，装完后重启 |
| Python 3.11 或 3.12 | 本机跑后端 | 不要用 3.13 |
| Node.js 18+（含 npm） | 本机跑前端 | 建议 LTS |
| 可选：DeepSeek API Key | 生成像样的中文答案 | 不配也能检索，回答会是占位句 |

国内拉 Docker 镜像若超时，在 Docker Desktop → **Settings → Docker Engine** 配置可用的 `registry-mirrors`（不要用已失效的中科大/网易源），然后 **Apply & Restart**。

---

## 二、第一次配置（只做一次）

在项目根目录 `F:\ai\code\text\enterprise-rag-agent`（或你自己的路径）打开终端。

**PowerShell：**

```powershell
Copy-Item .env.example .env
```

**Linux / macOS：**

```bash
cp .env.example .env
```

用记事本打开 `.env`：

- 开发可暂时不填 `DEEPSEEK_API_KEY`。
- 要用官方模型写回答时，填入 Key（**不要把 `.env` 提交到 Git**，仓库已忽略该文件）。
- 生产环境必须改掉 `APP_SECRET_KEY` 和默认数据库密码 `rag`。

---

## 三、启动数据库（后端、前端都依赖它）

Docker Desktop 左下角变成 **Running** 后，在**项目根目录**执行：

```powershell
cd F:\ai\code\text\enterprise-rag-agent
docker compose up -d postgres redis qdrant
docker compose ps
```

三个服务都要是 `healthy`（或至少 `running`）：

- PostgreSQL：本机 `5432`
- Redis：本机 `6379`
- Qdrant：本机 `6333`

**停中间件（一般开发不必停）：**

```powershell
docker compose stop postgres redis qdrant
```

**再启动：** 还是上面的 `docker compose up -d postgres redis qdrant`。

---

## 四、后端怎么启动（详细）

后端必须用**单独一个终端**，一直开着。管理员权限的终端可以用，但不是必须。

### 4.1 进入后端目录、安装依赖

优先用 [uv](https://docs.astral.sh/uv/)：

```powershell
cd F:\ai\code\text\enterprise-rag-agent\backend
uv sync
```

如果没有 `uv`，用已安装的 Python：

```powershell
cd F:\ai\code\text\enterprise-rag-agent\backend
python -m pip install -e .
```

（可选）装向量模型库后检索更准，体积较大：`pip install sentence-transformers`

### 4.2 建表（第一次或迁移更新后必做）

确认第 3 步里 postgres 已经 healthy：

```powershell
cd F:\ai\code\text\enterprise-rag-agent\backend
python -m alembic upgrade head
```

有 uv 时也可以：`uv run alembic upgrade head`

### 4.3 启动 API 服务

```powershell
cd F:\ai\code\text\enterprise-rag-agent\backend
python -m uvicorn app.main:app --reload --port 8000
```

有 uv 时：`uv run uvicorn app.main:app --reload --port 8000`

看到类似 `Uvicorn running on http://127.0.0.1:8000` 即成功。

| 地址 | 作用 |
|------|------|
| http://localhost:8000/docs | 接口文档（Swagger） |
| http://localhost:8000/api/v1/health | 健康检查，`postgres`/`redis`/`qdrant` 应为 `true` |

`APP_ENV` 不是 `prod` 时，启动成功会自动写入开发账号（库里还没有 demo 租户才会写）：

- 租户 slug：`demo`
- 用户名：`admin`
- 密码：`Admin@123456`

### 4.4 停掉后端

在跑 uvicorn 的那个窗口按 **`Ctrl+C`**。

窗口已经关了但 8000 仍被占用时：

```powershell
netstat -ano | findstr :8000
taskkill /PID 这里填PID数字 /F
```

改完 Python 代码后：若用了 `--reload` 会自动重启；没有的话再执行一次 4.3。

---

## 五、前端怎么启动（详细）

前端也要**另开一个终端**，不要和后端挤在同一个窗口里前台同时跑。

### 5.1 安装依赖（第一次，或 `package.json` 变了之后）

```powershell
cd F:\ai\code\text\enterprise-rag-agent\frontend
npm install
```

### 5.2 启动开发服务器

```powershell
cd F:\ai\code\text\enterprise-rag-agent\frontend
npm run dev
```

浏览器打开：**http://localhost:5173**

开发服务器会把页面上的 `/api` 转发到 `http://localhost:8000`，所以**后端必须已经在 8000 端口运行**。

未登录访问 `/chat` 会跳到 `/login`。用上面的 `demo` / `admin` / `Admin@123456` 登录。

### 5.3 停掉前端

跑 `npm run dev` 的窗口按 **`Ctrl+C`**。

---

## 六、本地开发推荐顺序（小结）

1. 打开 Docker Desktop  
2. `docker compose up -d postgres redis qdrant`  
3. 终端 A：`alembic upgrade head` → `uvicorn ... --port 8000`  
4. 终端 B：`npm run dev`  
5. 浏览器打开 5173 → 登录 → 建知识库 → 上传文档等到 `ready` → 新建会话再提问  

问答检索不依赖 DeepSeek；要把检索结果写成通顺回答，再在 `.env` 填 `DEEPSEEK_API_KEY` 并**重启后端**。

---

## 七、怎么部署（详细）

下面分「本机/单机用 Compose 部署」和「更接近生产的注意点」。当前 `docker-compose.yml` 已包含 postgres、redis、qdrant、backend、frontend；`nginx/` 配置已写好，**尚未作为 Compose 服务挂上**，生产建议后续把 80 端口交给 Nginx。

### 7.1 服务器上准备

1. 安装 Docker 与 Docker Compose 插件。  
2. 把代码放到服务器（git clone 或打包上传）。**不要上传本机 `.env` 到公开仓库。**  
3. 在服务器新建 `.env`（可从 `.env.example` 复制后改）：

```env
APP_ENV=prod
APP_SECRET_KEY=换成至少32位随机串
POSTGRES_PASSWORD=换成强密码
DATABASE_URL=postgresql+asyncpg://rag:你的强密码@postgres:5432/rag
DEEPSEEK_API_KEY=你的Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
CORS_ORIGINS=https://你的域名
INLINE_DOCUMENT_PIPELINE=true
```

Compose 里 backend 会覆盖 `DATABASE_URL` / `REDIS_URL` / `QDRANT_URL` 为容器主机名，本机 `localhost` 那一套只给「本机 Python 跑后端」用。

### 7.2 用 Compose 一键构建并启动（含前后端容器）

在项目根目录：

```bash
docker compose up --build -d
```

含义：

- 构建 backend、frontend 镜像  
- 自动 `alembic upgrade head`（见 compose 里 backend 的 `command`）  
- 后端容器：`http://服务器IP:8000`  
- 前端开发服务器容器：`http://服务器IP:5173`（当前 Dockerfile 是 `npm run dev`，适合演示；正式生产应改为 `npm run build` 后由 Nginx 托管静态文件）

查看是否起来：

```bash
docker compose ps
docker compose logs -f backend
```

浏览器：

- 前端：http://服务器IP:5173  
- 接口文档：http://服务器IP:8000/docs（生产环境建议关掉 docs）

停止整套：

```bash
docker compose down
```

只停应用、保留数据卷（数据库不会删）：

```bash
docker compose stop
```

**删除数据（危险）：** `docker compose down -v` 会清掉 postgres/qdrant 里的内容。

### 7.3 用 Nginx 反代（生产建议）

`nginx/nginx.conf` 已经配置：

- `/` → 前端静态页  
- `/api/` → 后端，且 **`proxy_buffering off`**（聊天 SSE 必须关缓冲，否则字出不来）

落地时典型步骤：

1. 前端执行 `npm run build`，把 `frontend/dist` 拷到 Nginx 的 html 目录。  
2. 用该 conf 作为站点配置，`proxy_pass` 指向后端容器名或 `127.0.0.1:8000`。  
3. 浏览器只开放 **80/443**，不要把 5432、6379、6333 映射到公网。  
4. HTTPS 用证书（Let’s Encrypt 等）再包一层。

### 7.4 部署后验收清单

- [ ] 用管理员账号能登录  
- [ ] 能创建知识库并上传文档，状态变为 `ready`  
- [ ] 问文档里有的内容，有来源或 `[S1]`  
- [ ] 问无关内容会提示知识库未覆盖  
- [ ] 健康检查三个依赖为 true  
- [ ] `.env` 未进 Git，Key 只在服务器上  

### 7.5 大模型怎么部署

- **省钱默认：** `.env` 里配官方 `DEEPSEEK_API_KEY`，backend 容器能出网即可。  
- **内网本地模型：** 另起 Ollama/vLLM，把 `DEEPSEEK_BASE_URL` 改成例如 `http://ollama:11434/v1`，`DEEPSEEK_API_KEY` 填任意非空字符串，`DEEPSEEK_MODEL` 填本地模型名。不要把模型权重打进 FastAPI 镜像。

---

## 目录说明

```text
backend/      FastAPI 接口、检索、Agent
frontend/     Vue 3 页面
nginx/        反代示例配置
docker-compose.yml
.env.example  配置模板（可提交）
.env          真实密钥（不可提交）
```
