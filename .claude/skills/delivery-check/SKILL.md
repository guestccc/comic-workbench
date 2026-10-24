---
name: delivery-check
description: 交付前验证——代码改动提交或交付前必读并执行。检查蓝图同步、后端测试、前端构建、故事结构脚本与业务不变量，避免展示/复制/导出/写回不一致。
---

# 交付前验证

## 何时使用

以下任一情况命中时，在交付或提交前执行本技能：

- 修改了数据模型、编号、章节、页面、提示词、别名、导出逻辑；
- 修改了前端展示、复制、导出中任一与业务事实相关的路径；
- 修改了 Claude / DeepSeek 生成与写回逻辑；
- 用户要求「检查一下」「交付」「提交」「给我结果」。

## 执行步骤

### 1. 蓝图一致性

- 阅读根目录 `AGENTS.md` 与 `.ai/blueprints/INDEX.md`；
- 确认相关蓝图已更新，且 `变更历史` 记录了本次改动；
- 确认蓝图中的 `Impacted Files` 与本次实际改动一致；
- 如果代码改了但蓝图没改，先补蓝图，不要直接交付。

### 2. 后端测试

```bash
cd backend
uv run pytest
```

失败时先修复；不得跳过失败测试后继续交付。

### 3. 前端测试与构建

```bash
cd frontend
npm test
npm run build
```

必须通过 Vitest 测试、TypeScript 检查与 Vite 构建。

### 4. 受影响故事的结构检查

对本次涉及的故事 ID 执行：

```bash
python .claude/skills/story-breakdown/mapping_check.py --story-id <ID>
python .claude/skills/story-breakdown/script_check.py --story-id <ID>
python .claude/skills/story-breakdown/chapter_check.py --story-id <ID>
python .claude/skills/delivery-check/audit.py --story-id <ID>
```

涉及单章改动时，额外执行：

```bash
python .claude/skills/story-breakdown/script_check.py --story-id <ID> --chapter <N>
```

全量交付前执行：

```bash
python .claude/skills/delivery-check/audit.py
```

未通过时先修数据或代码，不得只修检查脚本绕过。

### 5. 跨层一致性抽查

至少确认：

- 展示页码 = 复制首行页码 = `image_prompt`【页码】；
- 章节正文档数、总图数与实际页面一致；
- 最终别名存在于候选列表，发文正文前缀与最终别名一致；
- 页面引用的角色名存在于角色卡；
- 图片 URL 与实际文件一致（如涉及资源改动）。

### 6. 报告

交付时明确报告：

- 执行了哪些检查；
- 通过 / 失败项；
- 未覆盖或需要用户确认的事项；
- 如执行了数据修复，说明修改范围与数量。

## 禁止事项

- 不得用「构建通过」代替业务不变量检查；
- 不得为了让检查通过而静默删除用户数据；
- 不得在蓝图未更新时交付跨模块契约变更；
- 不得只修展示路径而不检查复制、导出、写回路径。
