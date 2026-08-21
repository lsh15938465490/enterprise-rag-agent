# RAG+Agent 平台 — 实现计划

> 依据根目录 `project-design-doc.md`（PDD v1.0）。表名、接口路径、字段一律按 PDD，本文只把开发拆成可照着做的步骤。  
> 一个人按 **步骤 1 → 步骤 20** 往下做即可。两个人时，看每步里的「可同时做」。

---

## 阅读说明

- 共 **20 步**。每一步都写清：做什么、改哪些文件、做到什么算完成。
- **必须先做完上一步（或标明的依赖）再进入下一步**，除非该步写了可以并行。
- 前后端从 **步骤 1 做完之后** 就可以分开做：后端从步骤 2，前端从步骤 3。

```text
步骤1  搭仓库和数据库容器
   ├─ 步骤2  后端 FastAPI 空项目          ┐ 可同时做
   └─ 步骤3  前端 Vue3 空项目            ┘
步骤4  建数据库表
   └─ 步骤5  登录接口（JWT）
        ├─ 步骤6  前端登录页              ┐
        ├─ 步骤7  用户管理接口            │ 可同时做
        └─ 步骤8  知识库接口              ┘
             ├─ 步骤9  文档上传接口       ┐
             ├─ 步骤10 前端知识库/文档页  │
             ├─ 步骤14 会话接口           │ 可同时做
             └─ 步骤19 前端用户管理页     ┘
步骤11 解析切块（可与步骤13算法单测穿插）
步骤12 向量入库
步骤13 检索算法（可从步骤4起提前写单测）
步骤15 问答 SSE（后端）
步骤16 聊天页面（前端，会话列表可提前）
步骤17 Agent 工具  ┐ 可同时做
步骤18 限流审计    ┘
步骤20 Nginx 部署和总验收（最后做）
```

---

## 步骤 1：搭仓库目录和基础中间件

**目的**：让 PostgreSQL、Redis、Qdrant 在本机能跑起来，后面写代码有地方连。

**具体要做：**

1. 按 PDD 第 3 节建目录：`backend/`、`frontend/`、`nginx/`、`deploy/`、`backend/app/` 等空文件夹。
2. 写根目录 `docker-compose.yml`，先只加三个服务：
   - `postgres`：镜像 `postgres:16-alpine`，库名 `rag`，用户 `rag`，端口 `5432`
   - `redis`：端口 `6379`
   - `qdrant`：镜像 `qdrant/qdrant:v1.13.2`，端口 `6333`
3. 写 `.env.example`，字段必须与 PDD 第 10 节完全一致（先不用填真实 DeepSeek Key）。
4. 写 `README.md`：如何复制 `.env`、如何 `docker compose up -d postgres redis qdrant`。

**做到这就算完成：** 三个容器健康；浏览器或客户端能连上 `5432`、`6379`、`6333`。本步还不用跑业务接口。

**可同时做：** 无。必须最先完成。

---

## 步骤 2：搭 FastAPI 后端空项目

**目的**：后端能启动，所有接口将来都走同一套 JSON 返回格式。

**依赖：** 步骤 1。

**可同时做：** 和 **步骤 3** 一起做（一人后端、一人前端）。

**具体要做：**

1. 在 `backend/` 用 uv 初始化 Python 3.12，写 `pyproject.toml`，依赖至少包含：FastAPI、uvicorn、pydantic-settings、httpx。
2. 写 `app/core/config.py`，用 `BaseSettings` 读取 `.env` 里 PDD 列出的全部配置名。
3. 写 `app/core/logging.py`：JSON 日志，每条带 `request_id`。
4. 写 `app/main.py`：创建 FastAPI、CORS（`CORS_ORIGINS`）、lifespan。
5. 实现统一响应信封：`{ code, message, data, request_id }`；业务错误码按 PDD 第 7.1 节（`40001`、`40003` 等）。
6. 写 `GET /api/v1/health`，尝试探测 postgres / qdrant / redis，返回 `{ status, postgres, qdrant, redis }`。
7. 挂上 `app/api/v1/router.py`（本步可以只有 health）。

**做到这就算完成：** 本地 `uvicorn app.main:app --port 8000` 能启动；打开 `/docs` 看得到 OpenAPI；调用 health 返回信封，不是裸 JSON。

---

## 步骤 3：搭 Vue3 前端空项目

**目的**：前端能打开页面，路由和请求约定先定死。

**依赖：** 步骤 1。

**可同时做：** 和 **步骤 2** 一起做。

**具体要做：**

1. 在 `frontend/` 用 Vite 创建 Vue 3 + TypeScript 项目。
2. 安装：Vue Router、Pinia、Element Plus、axios、markdown-it（聊天页后面用）。
3. 按 PDD 第 9 节注册路由（页面文件可以先写标题占位）：
   - `/login`、`/chat`、`/chat/:conversationId`、`/kbs`、`/kbs/:id/docs`、`/history`、`/admin/users`
4. 写 `src/api/http.ts`：`baseURL = /api/v1`；成功时取出 `data`；失败时弹出 `message`。
5. 写简单布局：顶栏、侧栏、内容区。
6. 路由守卫：没有 token 时一律跳 `/login`（token 先读 `localStorage`，步骤 6 再接真登录）。

**做到这就算完成：** `npm run dev` 能打开登录页；直接访问 `/chat` 会被踢回登录页。

---

## 步骤 4：建数据库表和开发账号

**目的**：PDD 里的表在 PostgreSQL 里真实存在，开发环境有可登录用户。

**依赖：** 步骤 2。

**可同时做：** 和 **步骤 13** 一起做（步骤 13 先写不连库的切块/RRF 单测）。

**具体要做：**

1. 写 `app/db/session.py`（SQLAlchemy 2.0 async + asyncpg，连接 `DATABASE_URL`）。
2. 写 `app/db/models.py`，表必须与 PDD 第 5 节一致，包括：
   - `tenants`、`users`、`knowledge_bases`、`knowledge_base_acl`
   - `documents`、`chunks`（含 `content_seg`）、`conversations`
   - `conversation_knowledge_bases`、`messages`、`message_citations`、`audit_logs`
3. 建枚举：`user_role`、`doc_status`、`message_role`、`conversation_mode`。
4. 配置 Alembic，生成第一版迁移；迁移里要有 `search_tsv` 的触发器。
5. 开发环境种子数据（`APP_ENV=dev` 才执行）：
   - 租户名称 `Demo Corp`，slug `demo`
   - 用户 `admin` / `admin@demo.local` / 密码 `Admin@123456`，角色 `tenant_admin`
6. `APP_ENV=prod` 时禁止插入上述默认密码。

**做到这就算完成：** `alembic upgrade head` 成功；用 SQL 能查到 demo 租户和 admin 用户。

---

## 步骤 5：做登录、刷新令牌、当前用户接口

**目的**：后端认证可用，后面所有业务接口都靠这一步的 JWT。

**依赖：** 步骤 4。

**可同时做：** 本步建议单独做完。做完之后，步骤 6、7、8 可以三人分头。

**具体要做：**

1. 写 `app/core/security.py`：密码 bcrypt（cost=12）；access token 30 分钟；refresh token 7 天。
2. JWT payload 必须带 `user_id`、`tenant_id`。
3. 实现接口（均在 `/api/v1` 下）：
   - `POST /auth/login`，body：`tenant_slug`、`username`、`password`
   - `POST /auth/refresh`，body：`refresh_token`
   - `POST /auth/logout`：refresh 的 jti 写入 Redis 黑名单，TTL 7 天
   - `GET /auth/me`
4. 写 `app/core/deps.py`：`get_current_user`、`require_roles`。未登录返回 `code=40001`。
5. 写 `tests/test_auth.py`：密码错误失败；必须带租户 slug 登录。

**做到这就算完成：** 用 demo/admin 能拿到 `access_token`；不带 Token 调 `/auth/me` 失败；带 Token 能返回用户信息。

---

## 步骤 6：做前端登录页和自动刷新 Token

**目的**：人能从浏览器登录进系统。

**依赖：** 步骤 3 必须完成；和后端联调需要步骤 5。

**可同时做：** 步骤 5 开发时前端可用假数据；步骤 5 完成后，与 **步骤 7、步骤 8** 同时做。

**具体要做：**

1. 完善 `Login.vue`：三个输入框——租户 slug、用户名、密码；调用 `POST /auth/login`。
2. 写 `stores/auth.ts`：保存 `access_token`、`refresh_token`、用户信息。
3. 在 `http.ts` 里：收到 HTTP 401 时先调 `POST /auth/refresh` 再重试一次；刷新失败则清空状态并跳登录页。
4. 退出登录：调 `POST /auth/logout` 并清本地 token。

**做到这就算完成：** 输入 `demo` / `admin` / `Admin@123456` 能进入 `/chat`；刷新浏览器仍是登录状态；点退出回到登录页。

---

## 步骤 7：做用户管理接口

**目的**：租户管理员能在系统里开账号。

**依赖：** 步骤 5。

**可同时做：** 与 **步骤 6、步骤 8** 同时做。

**具体要做：**

1. `GET /users`：分页，`page`、`page_size`、`keyword`。
2. `POST /users`：`username`、`email`、`password`、`role`。
3. `PATCH /users/{id}`：可改 `is_active`、`role`、`password`。
4. 权限：仅 `tenant_admin` 和 `super_admin`。普通 `member` 返回 `code=40003`。
5. 密码规则：至少 8 位，且同时包含字母和数字。
6. 所有查询带 `tenant_id`，不能看到其他租户用户。

**做到这就算完成：** 管理员能创建 `kb_editor`；用 member 的 token 调这些接口被拒绝。

---

## 步骤 8：做知识库接口和 Qdrant 集合

**目的**：能创建知识库，并控制谁能看见。

**依赖：** 步骤 5。

**可同时做：** 与 **步骤 6、步骤 7** 同时做。

**具体要做：**

1. `GET /knowledge-bases`：只返回当前用户有权读的库。
2. `POST /knowledge-bases`：`name`、`description`；权限 `kb_editor` 及以上。
3. 创建时生成 `qdrant_collection = kb_{租户slug}_{去掉横线的知识库id}`，并在 Qdrant 建 collection：维度 1024、Cosine、HNSW。
4. `GET/PATCH /knowledge-bases/{id}`；`DELETE` 做软删除：`is_active=false`。
5. `PUT /knowledge-bases/{id}/acl`：配置哪些用户 `can_read` / `can_write`。
6. 未配 ACL 时：只有创建者和租户管理员能看见。

**做到这就算完成：** 两个普通用户默认看不到对方的库；授权后能看到；Qdrant 里出现对应 collection。

---

## 步骤 9：做文档上传、落盘、下载、删除

**目的**：文件先安全存下来，状态为 `uploaded`，解析放到步骤 11。

**依赖：** 步骤 8。

**可同时做：** 与 **步骤 10、步骤 14、步骤 19** 同时做。

**具体要做：**

1. 写 `app/services/storage.py`：保存路径必须是 `{tenant_id}/{kb_id}/{doc_id}/{文件名}`，禁止用户传入绝对路径。
2. 文件名用 `secure_filename`，只保留中英文、数字和 `._-`。
3. `POST /knowledge-bases/{kb_id}/documents`：`multipart` 字段名 `file`。
   - 只允许 `pdf/docx/txt/md`，大小 ≤ 50MB
   - HTTP **202**，返回 DocumentDTO，`status=uploaded`
4. `GET /knowledge-bases/{kb_id}/documents`：可按 status 筛选、分页。
5. `GET /documents/{id}`、`GET /documents/{id}/file`（附件下载）、`DELETE /documents/{id}`（本步删数据库行和磁盘文件；Qdrant 点位等步骤 12 补删）。
6. 本步投递 Celery 可以先空实现，或只打日志「等待解析」。

**做到这就算完成：** 上传后磁盘有文件、数据库有记录；错误后缀被拒绝；能下载原文件。

---

## 步骤 10：做前端「知识库」和「文档」两个页面

**目的**：编辑者能在界面上建库、上传文件、看解析状态。

**依赖：** 步骤 6；上传功能要等步骤 9 的接口。

**可同时做：** 与 **步骤 9、步骤 7、步骤 19** 同时做（可先做列表和创建库，上传按钮后接）。

**具体要做：**

1. `KnowledgeBases.vue`：列表、新建、编辑名称/描述。
2. `Documents.vue`：上传、文件名、大小、状态、失败原因 `error_message`。
3. 状态为 `failed` 时展示错误；提供「重新解析」按钮（接口未好时按钮禁用，步骤 11 后再启用）。
4. 按 `status` 筛选。

**做到这就算完成：** 登录后能创建知识库、上传一份文件、在表格里看到 `uploaded`（解析通了以后会变成 `ready`）。

---

## 步骤 11：做后台解析和切块

**目的**：上传的文件变成数据库里的文本块。

**依赖：** 步骤 9；切块规则与步骤 13 的单测保持一致。

**可同时做：** 前端可以同时做步骤 16 的会话列表（先不接真实问答）。不要和步骤 12 抢未测完的状态机。

**具体要做：**

1. 写 `app/workers/celery_app.py`，队列名称：`parse`、`embed`、`default`。
2. 写解析器：
   - PDF 用 `pypdf`，按页抽文本；没有文字则失败，`error_message=EMPTY_TEXT`
   - DOCX 用 `python-docx`，标题写入 `heading`
   - TXT/MD：先 utf-8，失败再试 gbk
3. 写切块：约 800 字一块，重叠 120 字；优先在空行和 `。` 切开；去掉长度小于 50 的块；用 jieba 写入 `content_seg`。
4. 状态变化：`uploaded` → `parsing` → `parsed` 或 `failed`。
5. 实现 `POST /documents/{id}/reprocess`：把状态改回 `uploaded` 再投递任务。
6. 写 `tests/test_chunker.py`。
7. `docker-compose` 增加 `worker` 服务（本步至少能在本机命令行跑 celery）。

**做到这就算完成：** 上传一份带文字的 PDF 后，`chunks` 表有数据，文档状态为 `parsed`；纯扫描件会失败。

---

## 步骤 12：做向量化并写入 Qdrant

**目的**：文档状态变为 `ready`，之后才能检索。

**依赖：** 步骤 11、步骤 8。

**可同时做：** 前端步骤 16 仍可用假的流式文字；**不能**对用户声称「检索已通」。

**具体要做：**

1. 写 `app/services/embeddings.py`：`embed_texts(list[str]) -> list[list[float]]`，批大小 32，向量做 L2 归一化，维度 1024。
2. 写 `app/services/qdrant_store.py`：upsert；payload 字段按 PDD 第 6.3 节一个不能少。
3. 状态变化：`parsed` → `embedding` → `ready` 或 `failed`。
4. 删除文档时：按 `document_id` 从 Qdrant 删点，并删 PostgreSQL 的 chunks。

**做到这就算完成：** 文档 `status=ready`；Qdrant 里的点数量等于 chunk 行数。

---

## 步骤 13：做混合检索算法（可提前写）

**目的**：把「向量结果 + 关键词结果」合成最终 8 条上下文。这一步很多代码不连服务器也能测。

**依赖：** 写纯函数只需步骤 2；接到数据库和 Qdrant 需要步骤 4、步骤 12。

**可同时做：** 从步骤 4 开始就可以和建表、写接口同时做，先保证单测通过，步骤 15 再接入。

**具体要做：**

1. 向量召回：Qdrant search，每库过滤 `tenant_id` + `knowledge_base_id`，`top_k=40`。
2. 关键词召回：PostgreSQL `tsvector`（用 `content_seg`），`top_k=40`。
3. RRF 融合：`分数 = 1 / (60 + 排名)`，同一 `chunk_id` 分数相加。
4. Rerank：取融合后最多 40 条，模型打分后留 `top_n=8`。
5. 若最高分小于 0.2：视为没有命中，后续回答必须说「当前知识库未覆盖该问题」。
6. 写 `tests/test_rrf.py`。
7. 函数签名对齐 PDD 第 16.2 节的 `retrieve(...)`。

**做到这就算完成：** 单测说明融合和去重正确；接入后只检索 `ready` 文档的 chunk。

---

## 步骤 14：做会话（对话列表）接口

**目的**：每个用户有自己的聊天会话，并且绑定知识库。

**依赖：** 步骤 5、步骤 8。

**可同时做：** 与 **步骤 9、步骤 10、步骤 19** 同时做。

**具体要做：**

1. `GET /conversations` 分页，按 `updated_at` 倒序，只返回当前用户。
2. `POST /conversations`：`mode` 为 `rag` 或 `agent`；`knowledge_base_ids` 至少 1 个，且校验 ACL。
3. `GET /conversations/{id}`：带最近 50 条消息。
4. `GET /conversations/{id}/messages` 分页。
5. `PATCH /conversations/{id}` 改标题；`DELETE /conversations/{id}`。
6. 测试：用户 A 不能读取用户 B 的会话。

**做到这就算完成：** 能新建会话并绑上知识库；跨用户访问返回 `40004` 或 `40003`。

---

## 步骤 15：做问答接口（RAG + SSE 流式）

**目的**：用户提问后，根据知识库流式返回答案和引用来源。

**依赖：** 步骤 12、步骤 13、步骤 14。

**可同时做：** 步骤 16 可先按下面的事件格式做假数据；接真实 DeepSeek 必须等本步。

**具体要做：**

1. 写 `app/services/llm_deepseek.py`：模型 `deepseek-chat`，RAG 温度 `0.3`，`max_tokens=2048`。
2. System Prompt 必须使用 PDD 第 8.4 节原文。
3. 历史只带最近 10 条消息；预估 token 超过 6000 从最旧开始丢掉。
4. `POST /chat/completions`，body：`conversation_id`、`question`、`stream`。
5. 先把用户问题写入 `messages`（role=user）。
6. `stream=true` 时：`Content-Type: text/event-stream`，不要 JSON 信封。事件类型：
   - `meta`、`delta`、`citation`、`done`、`error`
   - 本步先不要 `tool`（步骤 17 再加）
7. `stream=false` 时：走统一信封，data 为完整 assistant MessageDTO。
8. 答案落库 `messages` + `message_citations`；snippet 最多 240 字。
9. Nginx 尚未接入时，先用 Vite 代理或直连 `8000` 测 SSE。

**做到这就算完成：** 问文档里有的内容，答案含 `[S1]` 且有 citation；问完全无关的内容，回答「未覆盖」，不编造条款。

---

## 步骤 16：做前端聊天页和历史页

**目的**：用户在网页里完成提问、看流式答案和来源卡片。

**依赖：** 步骤 6、步骤 14；真实流式需要步骤 15。

**可同时做：** 步骤 14 一完成就可以做左侧会话列表和新建会话；步骤 11～15 期间用假 SSE 调 UI。

**具体要做：**

1. `Chat.vue`：
   - 左侧会话列表
   - 新建会话：多选知识库，切换 RAG / Agent
   - 右侧消息列表、输入框
2. 组件：`ChatMessage.vue`、`SourceCard.vue`、`StreamMarkdown.vue`（Markdown 渲染）。
3. 流式必须用浏览器 `fetch` + `ReadableStream`，不要用 axios。
4. 按 SSE 的 `event` 名字拼接文字；`citation` 渲染来源卡片，可点开展开 snippet。
5. `History.vue`：历史会话入口。
6. Agent 的 `tool` 事件先做一条灰色提示条，步骤 17 后再显示真实工具名。

**做到这就算完成：** 发送问题后文字逐字出现；来源卡片文件名正确；刷新页面记录还在。

---

## 步骤 17：做 Agent 工具调用

**目的**：Agent 模式下模型可以调白名单工具，但回答制度问题仍要走 RAG。

**依赖：** 步骤 15。

**可同时做：** 与 **步骤 18** 同时做。

**具体要做：**

1. `GET /tools` 返回：`get_weather`、`query_kb_stats`、`run_readonly_sql`（后一项默认 `enabled=false`）。
2. 实现三个工具文件，并由 `registry.py` 注册；名称必须在白名单内。
3. `get_weather`：没配 `WEATHER_API_KEY` 时返回「服务未配置」，不要报 500。
4. `run_readonly_sql`：只用 `sqlparse` 检查必须是单条 `SELECT`，超时 3 秒，最多 50 行，禁止系统表；仅租户管理员的 Agent 会话可开。
5. `agent_loop.py`：最多 5 轮；每一轮都要把检索结果放进上下文。
6. DeepSeek 温度 `0.2`；SSE 增加 `event: tool`（`running` / `done`）。
7. 写 `tests/test_sql_tool.py`：`DROP`、`INSERT`、多语句全部拒绝。

**做到这就算完成：** Agent 模式能调天气工具；问制度仍出现引用，不能只靠模型瞎编。

---

## 步骤 18：做限流、审计日志、日志脱敏

**目的**：接口不被打爆，关键操作留痕，日志不泄密。

**依赖：** 步骤 5；登录/上传/聊天限流需要对应路由已存在（步骤 9、步骤 15）。

**可同时做：** 与 **步骤 17** 同时做。

**具体要做：**

1. Redis 令牌桶，key 格式 `rl:{路由}:{用户或IP}`：
   - 登录：每个 IP 每分钟 10 次
   - 问答：每个用户每分钟 20 次
   - 上传：每个用户每分钟 10 次
2. 超限返回 `code=42901`，HTTP 429。
3. 写入 `audit_logs` 的动作：`login`、`upload`、`delete_doc`、`chat`。
4. 日志不得打印：密码、Token、文件全文。

**做到这就算完成：** 故意打满登录次数会限流；数据库能查到上传和问答审计。

---

## 步骤 19：做前端用户管理页

**目的**：管理员在界面里管账号，不必用 Swagger。

**依赖：** 步骤 6、步骤 7。

**可同时做：** 与 **步骤 9、步骤 10、步骤 14** 同时做。

**具体要做：**

1. 写 `AdminUsers.vue`：表格、搜索、新建用户、改角色、禁用。
2. 路由 `/admin/users`：仅 `tenant_admin` 和 `super_admin` 能进入，其他人跳走或提示无权限。

**做到这就算完成：** 管理员能从页面创建用户；用 member 账号打不开该页。

---

## 步骤 20：接 Nginx、打通全套 Compose、按清单验收

**目的**：用 80 端口像生产一样走一遍 PDD 第 18 节。

**依赖：** 步骤 10、16、17、18、19 尽量完成；至少保证「登录 → 上传 → 变 ready → 提问」通。

**可同时做：** 无。最后单独做。

**具体要做：**

1. `docker-compose.yml` 补齐：`backend`、`worker`、`frontend`（或静态产物）、`nginx`。
2. 写 `nginx/nginx.conf`：
   - `/` 指向前端
   - `/api/` 反代后端
   - **必须** `proxy_buffering off;`，否则 SSE 会卡住
3. 按下面清单逐项打勾：
   - [ ] demo 租户 admin 能登录
   - [ ] 创建知识库并上传中文 PDF，状态变为 `ready`
   - [ ] 问手册里有的条款，答案有 `[S1]`，来源文件名正确
   - [ ] 问无关问题，回答知识库未覆盖
   - [ ] Agent 模式能调用 `get_weather`
   - [ ] 用户 A 看不到用户 B 的会话
   - [ ] 经过 Nginx 后答案仍然是逐字出来的

**做到这就算完成：** 上述 7 条全部通过。v1 开发结束。

---

## 两人分工（对照步骤号）

| 谁 | 做哪些步骤 |
|----|------------|
| 后端 | 步骤 2、4、5、7、8、9、11、12、14、15、17、18 |
| 前端 | 步骤 3、6、10、16、19 |
| 都可以做 | 步骤 1、13、20 |

接口字段不要临时改名，一律以 PDD 第 7 节为准。后端没好时，前端用写死的 JSON 或 Mock 先画页面。

---

## 不要颠倒的顺序

1. 不要在步骤 12 完成前做真实问答（没有向量只能编造）。
2. 不要在步骤 15 完成前做 Agent。
3. 不要先做很炫的聊天页却不按 PDD 实现信封和 SSE 事件名。
4. 检索时必须带 `tenant_id` 和知识库 id 过滤，禁止全库扫描。
