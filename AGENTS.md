# SkillHub — AGENTS.md

> 只写 Agent 无法通过读代码自行发现的信息。每条都是一个"地雷"或非显而易见的约定。
> 如果 agent 读一遍代码就能发现 → 不要写在这里。

## Gotchas (必须知道)

- **bcrypt 版本陷阱** — passlib 与 bcrypt>=4.1 不兼容。项目用 bcrypt 原生 API，不要引入 passlib。详见 `docs/solutions/runtime-errors/passlib-bcrypt-incompatibility.md`。
- **JWT 无过期时间** — `create_token()` 不设 exp。重启后 token 失效（除非设了 `SKILLHUB_SECRET_KEY`）。生产环境必须设该 env var，否则每次重启所有用户被踢出。
- **CORS 全开** — `allow_origins=["*"]`。生产部署前必须收紧。
- **SQLite 单文件** — 不支持并发写入多服务器。多实例部署需换 DB。
- **Docker config 挂载** — `docker-compose.yml` 把 `~/.skillhub/config.yaml` 挂载为只读。首次 `docker compose up` 前必须创建该文件，否则容器启动后无法写入配置。
- **Skill name 是 upsert** — `POST /api/skills` 同名 skill 会更新而非报错。这是设计行为，不是 bug。注意：upsert 按 `(name, project_id)` 匹配，不同 project 下同名 skill 是独立的。
- **SQLite UNIQUE 与 NULL** — `UNIQUE(name, project_id)` 约束中，NULL != NULL。所以 `project_id=NULL` 的 skill 允许同名（向后兼容旧数据）。application 层需注意去重。

## Non-obvious Conventions

- **`list_cmd.py` 不是 `list.py`** — 避免与 Python 内置 `list` 冲突。CLI 命令名用 `cli.add_command(list_skills, "list")` 映射。
- **Tags 存为 JSON TEXT** — 不是关联表。`json.dumps/loads` 序列化，查询靠 LIKE。
- **Download 计数每次下载都+1** — 包括重复下载同一文件。用于热度排序，不是去重计数。
- **Admin bootstrap** — 首次启动从 config.yaml 的 `admin.username` + `admin.password_hash` 创建管理员。之后配置变更不再生效。生成 hash: `python -c "import bcrypt; print(bcrypt.hashpw(b'yourpass', bcrypt.gensalt()).decode())"`。
- **Project CRUD 需 admin** — `POST/PUT/DELETE /api/projects` 需要 admin 角色。`GET /api/projects` 只需登录。
- **Delete project 阻塞** — 如果 project 下有 skill，删除返回 409。必须先移除所有 skill 才能删除 project。
- **CLI --project 优先级** — CLI `--project` flag > config `default_project` > 无默认（返回所有 project 的 skill）。
- **Storage 路径带 project** — 新 skill 文件存放在 `skills_dir/<project_id>/<skill_id>/`。`project_id=NULL` 的 skill 存在 `skills_dir/default/<skill_id>/`。

## Production Environment

- **Server**: `ssh aliyun-zhengzhou` — 可查看日志和部署服务
- 部署方式: Docker Compose (skillhub + nginx)
- 数据持久化: Docker volumes `skillhub-data` / `skillhub-skills`

## Don't Write (agent 能自行发现)

以下内容不要放在 AGENTS.md 里（agent ls/read 就能知道）:
- 目录结构
- 技术栈列表 (FastAPI, SQLite, etc.)
- API 路由表 (agent 读 `api/` 目录即可)
- Pydantic 模型定义
- 测试命令 (pytest)
- 安装步骤 (README 里有)
