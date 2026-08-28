# SkillHub Roadmap

## 当前迭代：Harness 改造（2026-08-28）

用"驾驭工程之美"课程的 Harness 框架改造 SkillHub 的开发流程。

### 目标
- [x] 将 AGENTS.md 重构为 Harness 入口（双层循环 + 渐进式信息披露）
- [x] 创建 state/ 目录（状态子系统：roadmap + progress.json）
- [x] 创建 scripts/check.sh（自动化反馈控制）
- [x] 创建 docs/conventions/gotchas.md（gotchas 子文档）

### 验收标准
- Agent 读取 AGENTS.md 后能理解双层循环工作流
- `scripts/check.sh` 可执行并能输出结构化 PASS/FAIL
- 所有原有 gotchas 内容完整迁移到 docs/conventions/gotchas.md

---

## 已完成的功能

| 日期 | 功能 | 设计文档 |
|------|------|----------|
| 2026-08-14 | Multi-project mode | `docs/plans/multi-project-mode.md` |
| 2026-08-08 | 数据迁移（legacy skill 目录） | `docs/plans/2026-08-08-001-feat-migrate-skillhub-data-plan.md` |
| 2026-08-07 | Admin 页面项目管理 UI | — |
| 2026-08-07 | 用户管理（JWT + RBAC） | `docs/plans/2026-08-07-001-feat-user-management-plan.md` |
| 2026-07-23 | 下载计数 + UI 排序 | `docs/plans/2026-07-23-001-feat-download-count-plan.md` |
| 2026-07-23 | CLI install 改用 uv tool | `docs/plans/2026-07-22-001-refactor-cli-install-uv-tool-plan.md` |
| 2026-07-22 | 中文语言支持 | `docs/plans/2026-07-20-002-feat-chinese-language-support-plan.md` |
| 2026-07-21 | SkillHub 自有 Skill | `docs/plans/2026-07-21-001-feat-skillhub-docs-skills-plan.md` |
| 2026-07-20 | Docker + nginx + quickstart | `docs/plans/2026-07-20-004-feat-dockerfile-quickstart-plan.md` |
| 2026-07-18 | SkillHub MVP | `docs/plans/2026-07-18-001-hub-skillhub-plan.md` |

## 待做（Backlog）

按优先级排序，Agent 可以从这里领取下一个 task：

### 高优先级
- [ ] CORS 收紧 — 当前 `allow_origins=["*"]`，生产环境不安全
- [ ] JWT token 过期机制 — 当前 token 永不过期

### 中优先级
- [ ] Skill 版本管理 — 支持同一 skill 的多版本
- [ ] API 限流 — 防止滥用
- [ ] 审计日志 — 记录谁在什么时候做了什么操作

### 低优先级
- [ ] Skill 评分/评论系统
- [ ] Webhook 通知（发布/删除事件）
- [ ] 用户个人主页 / Dashboard

## 已知问题

暂无阻塞性问题。

## 技术债务

- [ ] 测试覆盖不足 — 目前只有 4 个测试文件，API 层测试需要加强
- [ ] CORS 全开需要收紧
- [ ] 缺少 CI 自动化测试（只有 deploy workflow）
