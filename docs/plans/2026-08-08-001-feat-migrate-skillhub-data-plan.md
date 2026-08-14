# feat: Migrate SkillHub data from zhengzhou NAS to aliyun-zhengzhou

**Date:** 2026-08-08
**Type:** feat
**Depth:** Lightweight
**Product Contract Source:** ce-plan-bootstrap

---

## Problem Frame

SkillHub 之前部署在 `ssh zhengzhou`（QNAP NAS）上，后来迁移到了 `ssh aliyun-zhengzhou`（阿里云服务器）。旧服务器上积累了 188KB 的 SQLite 数据库（~55 个 skills）和对应的 skill 文件目录。新服务器目前只有 40KB 数据库和 1 个 skill。需要把旧服务器的完整数据迁移到新服务器上。

## Source Information

- **Source server:** `ssh zhengzhou` — QNAP NAS, Docker via Container Station
- **Source DB:** `/var/lib/docker/volumes/skill-hub-new_skillhub-data/_data/skillhub.db` (188KB, last modified Aug 6)
- **Source skills:** `/var/lib/docker/volumes/skill-hub-new_skillhub-skills/_data/` (~55 dirs)
- **Source Docker volume names:** `skill-hub-new_skillhub-data`, `skill-hub-new_skillhub-skills`

## Destination Information

- **Destination server:** `ssh aliyun-zhengzhou` — 阿里云服务器, Docker Compose
- **Destination DB:** `/var/lib/docker/volumes/skillhub_skillhub-data/_data/skillhub.db` (40KB)
- **Destination skills:** `/var/lib/docker/volumes/skillhub_skillhub-skills/_data/` (1 dir)
- **Destination Docker volume names:** `skillhub_skillhub-data`, `skillhub_skillhub-skills`
- **Container name:** `skillhub-skillhub-1`
- **Compose file:** `/root/skillhub/docker-compose.yml`

## Scope Boundaries

### In scope
- SQLite 数据库迁移（skillhub.db）
- Skill 文件目录迁移（所有 UUID 子目录）
- 服务停启和数据验证

### Out of scope
- 代码变更（代码已经是最新的）
- 数据库 schema 迁移（schema 兼容）
- Docker 镜像更新

---

## Implementation Units

### U1. 停止目标服务器上的 SkillHub 容器

**Goal:** 确保数据库和文件在迁移期间不被写入

**Dependencies:** None

**Files:** `docker-compose.yml` (只读，用于理解挂载结构)

**Approach:**
- 通过 `ssh aliyun-zhengzhou` 执行 `docker compose -f /root/skillhub/docker-compose.yml stop`
- 验证容器已停止：`docker ps --filter name=skillhub` 确认无运行实例

**Test scenarios:**
- Happy path: `docker ps` 输出中无 `skillhub-skillhub-1` 运行
- Edge case: 如果容器不存在，`docker compose stop` 应成功（幂等）

**Verification:** `docker ps --filter name=skillhub` 输出为空

---

### U2. 从源服务器复制数据到目标服务器

**Goal:** 将完整的 SQLite 数据库和 skill 文件目录传输到新服务器

**Dependencies:** U1

**Files:** 
- 源：`/var/lib/docker/volumes/skill-hub-new_skillhub-data/_data/skillhub.db`
- 源：`/var/lib/docker/volumes/skill-hub-new_skillhub-skills/_data/` (全部内容)
- 目标：`/var/lib/docker/volumes/skillhub_skillhub-data/_data/skillhub.db`
- 目标：`/var/lib/docker/volumes/skillhub_skillhub-skills/_data/` (全部内容)

**Approach:**
- 使用 `scp` 或 `rsync` 从 zhengzhou 直接复制到 aliyun-zhengzhou（两台服务器应该能互相 SSH）
- 如果两台服务器不能直连，可通过本地中转（先 scp 到本地，再 scp 到目标）
- 数据库文件：`scp zhengzhou:/var/lib/docker/volumes/skill-hub-new_skillhub-data/_data/skillhub.db /tmp/skillhub.db` 然后 `scp /tmp/skillhub.db aliyun-zhengzhou:/var/lib/docker/volumes/skillhub_skillhub-data/_data/skillhub.db`
- Skills 目录：`rsync -avz zhengzhou:/var/lib/docker/volumes/skill-hub-new_skillhub-skills/_data/ /tmp/skillhub-skills/` 然后 `rsync -avz /tmp/skillhub-skills/ aliyun-zhengzhou:/var/lib/docker/volumes/skillhub_skillhub-skills/_data/`

**Test scenarios:**
- Happy path: 目标服务器上的 skillhub.db 文件大小与源一致（~188KB）
- Happy path: 目标服务器上的 skills 目录包含 ~55 个子目录
- Edge case: 如果目标已有 skillhub.db，覆盖即可（源数据更新）
- Error path: 如果网络中断，rsync 可以断点续传

**Verification:** 
- `ssh aliyun-zhengzhou "ls -la /var/lib/docker/volumes/skillhub_skillhub-data/_data/skillhub.db"` 确认大小匹配
- `ssh aliyun-zhengzhou "ls /var/lib/docker/volumes/skillhub_skillhub-skills/_data/ | wc -l"` 确认目录数 ≈ 55

---

### U3. 修复文件权限并重启服务

**Goal:** 确保迁移后的文件对容器进程可读，服务正常启动

**Dependencies:** U2

**Files:** 无代码变更

**Approach:**
- 检查并修复目标文件的 owner/permission（源服务器 UID=1000，目标可能是 admin:admin）
- 启动容器：`docker compose -f /root/skillhub/docker-compose.yml up -d`
- 验证健康检查通过

**Test scenarios:**
- Happy path: `docker ps` 显示 `skillhub-skillhub-1` 状态为 `Up` 且 `(healthy)`
- Happy path: `curl http://8.145.55.245:8000/api/health` 返回 200
- Happy path: `curl http://8.145.55.245:8000/api/skills` 返回 skill 列表，数量 ≈ 55
- Error path: 如果权限不对，容器可能启动但数据库打开失败 — 查看 `docker logs`

**Verification:**
- `curl -s http://8.145.55.245:8000/api/skills | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Total skills: {len(d)}')"` 显示约 55 个 skill

---

## Key Technical Decisions

1. **直连 vs 中转** — 优先尝试两台服务器直连（scp/rsync），如果 SSH 不互通则通过本地中转。这是唯一的技术分叉点。

2. **文件权限** — 源服务器 UID=1000，目标可能是 admin（UID 不同）。如果容器内以 appuser 运行，需要确认 UID 映射。可以 `chown -R 1000:1000` 或根据目标容器实际用户调整。

3. **数据库完整性** — 直接复制 SQLite 文件是安全的（容器已停止，无并发写入）。不需要 WAL checkpoint，因为源容器已停运。

## Risks

- **SSH 互通性** — 两台服务器可能不能直连，需要本地中转。中转会增加时间但不影响正确性。
- **权限不匹配** — 如果目标容器用户 UID 与 1000 不同，可能需要 chown。
- **数据覆盖** — 目标服务器上的现有数据（40KB DB, 1 skill）会被完全覆盖。这是预期行为。

## Deferred to Follow-Up Work

- 清理源服务器上的 Docker 资源（可选，不紧急）
- 确认 GitHub Actions CI/CD 的 DEPLOY_HOST 指向正确的服务器

---

## Verification Contract

1. `curl http://8.145.55.245:8000/api/health` → HTTP 200
2. `curl http://8.145.55.245:8000/api/skills` → 返回 ~55 个 skill 的 JSON 数组
3. 检查几个已知 skill 是否在列表中（从源 DB 中查询 skill 名称作为抽查）

## Definition of Done

- 目标服务器上的 SkillHub 服务正常运行
- 数据库包含完整的 ~55 个 skill 记录
- Skill 文件目录完整（~55 个 UUID 子目录）
- API 端点正常响应
