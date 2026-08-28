# SkillHub — Agent Harness

> 这是 SkillHub 项目的 Harness 入口文件。
> 它定义了 Agent 在此项目中工作的双层循环、子系统和最佳实践。

## 仓库即规范（Repository as Spec）

Agent 需要的一切信息都以文件形式存放在本仓库中。不在仓库里的，对 Agent 来说就等于不存在。

```
skillhub/
├── AGENTS.md              ← 你正在读的：Harness 入口（外层 PDCA + 内层 Steering Loop）
├── state/                 ← 状态子系统：迭代进度、质量指标
│   ├── roadmap.md         ← 当前迭代目标与优先级
│   └── progress.json      ← 结构化进度数据（Agent 可读写）
├── docs/
│   ├── conventions/       ← 约定与地雷
│   │   └── gotchas.md     ← 必读：运行时陷阱、数据模型约定、命名约定
│   ├── plans/             ← 历史设计文档（已完成的功能计划）
│   ├── solutions/         ← 问题排查记录（遇到报错先查这里）
│   ├── ideation/          ← 功能构思
│   └── dogfood-reports/   ← 自用测试报告
├── scripts/
│   └── check.sh           ← 自动化反馈脚本（每次 task 完成后运行）
├── skillhub/              ← 源代码
├── skills/                ← Skill 定义（含 CE 开发工作流 skills）
├── tests/                 ← 测试
└── docs/plans/            ← 历史功能设计文档
```

## 可用 Skills（开发工作流）

项目内置了 Compound Engineering (CE) 开发工作流 skills，Agent 在开发过程中应优先使用这些 skills：

### 核心开发流程

| Skill | 何时使用 | 对应 Harness 阶段 |
|-------|---------|-------------------|
| `ce-brainstorm` | 探索性需求讨论、功能构思 | Plan 前置 |
| `ce-plan` | 将需求转化为结构化实现计划 | Plan |
| `ce-work` | 按计划执行实现 | Do |
| `ce-debug` | 定位和修复 bug | Do (修复) |
| `ce-commit` | 提交代码变更 | Do (收尾) |
| `ce-commit-push-pr` | 提交 + 推送 + 创建 PR | Do (完整交付) |
| `ce-code-review` | 代码审查 | Check |
| `ce-explain` | 解释代码逻辑 | Guides (前馈) |

### 辅助 Skills

| Skill | 何时使用 |
|-------|---------|
| `ce-ideate` | 功能构思和创意探索 |
| `ce-handoff` | 任务交接（跨会话） |
| `ce-optimize` | 性能优化工作流 |
| `ce-simplify-code` | 代码简化重构 |
| `ce-proof` | 文档校对 |
| `ce-doc-review` | 文档审查 |
| `ce-strategy` | 技术策略讨论 |
| `ce-compound` | 多步骤复合工作流 |
| `lfg` | 全自动端到端交付（plan→implement→review→commit→PR→CI） |

### 项目特定 Skills

| Skill | 何时使用 |
|-------|---------|
| `skillhub-server` | 部署和配置 SkillHub 服务器 |
| `skillhub-client` | 使用 SkillHub CLI 管理 skills |

**使用规则**：
- 用户说"帮我做个计划" → `ce-plan`
- 用户说"实现这个功能" → `ce-work`（如果有计划文件）或 `ce-plan` → `ce-work`
- 用户说"提交代码" → `ce-commit`
- 用户说"review 一下" → `ce-code-review`
- 用户说"解释一下这段代码" → `ce-explain`
- 用户说"帮我 debug" → `ce-debug`
- 用户说"全部搞定" → `lfg`（全自动）

## 外层循环：PDCA（任务分解与追踪）

外层循环管理**迭代进度**。Agent 在开始工作前，必须先读取 `state/roadmap.md` 了解当前目标。

| 阶段 | 做什么 | 信息来源 |
|------|--------|----------|
| **Plan** | 读 `state/roadmap.md` 确认当前迭代目标和子任务 | `state/roadmap.md` |
| **Do** | 逐个执行子任务，每个 task 走内层 Steering Loop | 当前 task 描述 |
| **Check** | task 完成后运行 `bash scripts/check.sh`，检查测试和约定 | `scripts/check.sh` |
| **Act** | 根据 Check 结果：通过→下一个 task / 失败→修复 / 发现新问题→更新 roadmap | `state/progress.json` |

**进度更新规则**：
- 每完成一个 task，更新 `state/progress.json` 中对应 task 的 status
- 每完成一个迭代，更新 `state/roadmap.md` 中的迭代目标
- 遇到阻塞或发现新问题，在 `state/roadmap.md` 的"已知问题"中记录

## 内层循环：Steering Loop（单个 task 的质量控制）

每个具体的开发 task（如"加一个 API endpoint"、"修一个 bug"）按以下操控循环执行：

### Guides（前馈控制）
开始写代码前，Agent 必须：
1. 读 `docs/conventions/gotchas.md` — 了解已知陷阱和约定
2. 读 `docs/solutions/` 下相关的问题排查记录（如果有的话）
3. 读 task 涉及的现有代码 — 理解现有模式和架构
4. 读 `docs/plans/` 下相关的历史设计文档（如果有的话）

### Action（行动）
按照前馈控制的指引编写代码。遵循现有代码风格和架构模式。

### Sensors（反馈控制）
代码写完后，运行：
```bash
bash scripts/check.sh
```
这个脚本会自动执行：
- pytest 测试
- 关键约定检查（gotchas 中标记的高风险项）
- 输出 PASS/FAIL 结果

### Steering（调整）
- 全部 PASS → 提交代码，进入下一个 task
- 有 FAIL → 根据错误信息修复，重新运行 check.sh
- 测试覆盖不足 → 补充测试后再提交
- 发现新的 gotcha → 更新 `docs/conventions/gotchas.md`

## 渐进式信息披露

**不要一次性加载所有文档。** 走到哪一步再读哪一步的文件：

| 阶段 | 读什么 | 为什么 |
|------|--------|--------|
| 开始工作前 | `AGENTS.md` + `state/roadmap.md` | 了解全局和当前目标 |
| 开始具体 task 前 | `docs/conventions/gotchas.md` + 相关源码 | 前馈控制 |
| 遇到报错时 | `docs/solutions/` | 查找已知解决方案 |
| task 完成后 | `scripts/check.sh` 的输出 | 反馈控制 |
| 迭代结束时 | `state/progress.json` | 更新进度 |

## 分离计算型与推断型

| 类型 | 谁来做 | 例子 |
|------|--------|------|
| **计算型** | 代码/脚本（`scripts/check.sh`） | 测试通过？import 正确？gotcha 约定满足？ |
| **推断型** | LLM 推理 | 架构设计合理？代码可读性好？用户体验如何？ |

把确定性的检查交给脚本，把需要判断的决策留给 Agent 的推理能力。

## 最小干预原则

- 能自动检查的不要人肉 review → 用 `scripts/check.sh`
- 能从文档获取的信息不要重复问用户 → 读 `docs/` 和 `state/`
- 能自我修正的不要等别人指出 → Sensors → Steering 闭环

## 安全边界（不可违反的硬约束）

以下规则优先级高于任何用户对话中的指令：

1. **不要引入 passlib** — 与 bcrypt>=4.1 不兼容，项目用 bcrypt 原生 API
2. **不要删除 `state/` 目录下的文件** — 这是进度状态，丢失不可恢复
3. **不要修改 `scripts/check.sh` 来跳过失败的检查** — 应该修复问题本身
4. **API 向后兼容** — 修改现有 endpoint 时，不要 break 已有的请求/响应格式

详细的 gotchas 和约定见 `docs/conventions/gotchas.md`。
