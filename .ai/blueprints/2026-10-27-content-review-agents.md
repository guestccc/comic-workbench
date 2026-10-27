# 内容审阅 Agent 与视觉单元标准

- 状态：实施中（P0）
- 日期：2026-10-27
- 范围：`mapping-director` / `narration-editor` / `storyboard-director` 的职责与契约、视觉单元拆分标准、确定性检查补充

## 1. 背景与目标

条漫的核心质量在拆分与旁白：

- 分镜对照段要么一页塞多个动作，要么半句话一页；
- 主旁白容易写成剧情摘要，副旁白容易丢事实；
- `mapping_check.py` 只验证拼接覆盖，`script_check.py` 只验证页码、字数和必填字段，都不判断「一页能不能画出来」。

目标：把「可判定的规则」留给脚本，把「需要审美与语义判断的」交给只读 agent；agent 不写回数据库，主会话确认后再落库。

## 2. 三层分工

| 层 | 负责 | 不负责 |
|---|---|---|
| `story-breakdown` 技能 | 生成优化文、mapping、分镜页、章节、提示词 | 质量审片、人工决策 |
| 检查脚本 | 页码、覆盖、字数、章节上限、提示词页码等确定性规则 | 语义、节奏、连续性 |
| 内容 agent | 视觉单元、旁白质量、机位节奏、图文一致性 | 写回、改源数据、替代脚本 |

## 3. 核心设计决策

1. **视觉单元标准是唯一拆分依据**：SKILL 与 agent 都引用同一套标准，不各自发明。
2. **三个 agent 都做，mapping-director 先落地**：它是后面所有页、章节、图片的地基；旁白与审片 agent 紧随其后，不做取舍。
3. **agent 只读**：不调用写接口、不改数据库、不改项目文件；提案由主会话确认后写回。
4. **propose 与 review 分离**：propose 从优化文重新拆；review 审已有 mapping 的过载 / 过碎 / 不完整。
5. **确定性优先**：能用脚本判断的（字数、气泡数、页码、机位重复）先写脚本，不交给 agent。
6. **agent 输出必须可执行**：逐段 / 逐页给出问题、证据、建议；禁止「这段不太好」这类泛泛结论。
7. **不凭空补剧情**：agent 只能使用优化文、mapping、pages、角色卡与画风数据，不得编造原文没有的事实。
8. **风险分级用于减少决策量**：agent 给风险，服务端再叠加确定性风险；低风险可自动通过（见审阅工作台蓝图）。

## 4. 视觉单元标准

一页最多包含：

| 维度 | 上限 |
|---|---|
| 时间点 | 1 个瞬间 |
| 地点 | 1 个场景 |
| 人物 | 1–3 个主要人物，无人物进出改变关系 |
| 动作链 | 1 条「起因 → 动作 → 结果」 |
| 台词 | 1 个来回，≤2 个气泡 |
| 情绪 | 1 个情绪点或 1 次转折 |
| 信息 | 1 个信息点 |

必须拆：

- 时间跳跃、回忆切换、地点变化；
- 两个以上连续动作需要不同画面；
- 超过 2 句关键台词；
- 动作、回忆、背景解释混在一页；
- 人物进入 / 离开并改变场景关系。

必须合并：

- 相邻段同一时间、地点、动作链；
- 某段只有半个动作或半句台词，结果在下一句；
- 短句不是完整微动作；
- 合并后仍能在一张图里表达。

完整性：

- 每段 `summary` 必须是完整句：谁 + 在哪 + 做了什么 + 结果 / 情绪；
- 不得从动作或台词中间切断，除非下一段是刻意的反应特写；
- `source_text` 必须是原文连续子串，不得改写、补写、删标点；
- 所有 `source_text` 按顺序拼接必须与 `optimized_content` 逐字一致（含标点与换行）。

## 5. Agent 契约

### 5.1 通用约束

| 项目 | 约束 |
|---|---|
| 上下文 | 独立会话，不使用 fork；brief 必须包含故事 ID、模式、范围 |
| 数据源 | `GET /api/stories/<ID>/breakdown`；后端不可用时只读 SQLite |
| 写权限 | P0/P1 禁止 POST / PATCH / PUT / DELETE；禁止改项目文件；只可写临时文件。P2 若接入草稿，只能写 `mapping_reviews` 草稿表，仍禁止写源数据 |
| 工具 | `Read` / `Grep` / `Glob` / `Bash`（只读命令） |
| 输出 | 结构化 Markdown 或 JSON；每条含页码 / 段落、问题、证据、建议 |
| 引用 | 结论必须引用 `source_text` 或页面字段，不得只给主观评价 |

### 5.2 `mapping-director`

| 模式 | 输入 | 输出 |
|---|---|---|
| `propose` | 优化文、现有 mapping（参考）、章节、画风 | 完整候选 mapping + 差异摘要；由 `proposal_to_changes.py` 转换为 `MappingReviewChange[]` |
| `review` | 现有 mapping、优化文 | 过载 / 过碎 / 不完整清单；建议的拆并变更 |

检查重点：

- 每段是否一个视觉单元；
- `summary` 是否完整句；
- 是否跨时间 / 地点 / 动作链；
- 是否超过 2 个气泡；
- 是否为半拍动作；
- 是否把章节编号单独成页。

### 5.3 `narration-editor`

| 检查项 | 判定 |
|---|---|
| 主旁白 | <15 个汉字，是钩子不是摘要 |
| 副旁白 | <50 个汉字、≤2 行、能独立看懂 |
| 连读 | 所有 `narration_sub` 按页码拼接是否连贯 |
| 事实 | 姓名、地点、数字、结果是否保留 |
| 称谓 | 主角用「我」，其他人直呼姓名，禁「他 / 她」代词 |
| 回忆 | 是否标注「（回忆）」与时间 / 起因 |
| 标红 | 是否为主 / 副旁白连续片段，是否值得标红 |
| 台词 | 是否来自原文、是否超过 2 条、是否有新增 |

输出：逐页 `{page_number, field, severity, issue, evidence, suggestion}`；只给建议，不改写入库。

### 5.4 `storyboard-director`

| 检查项 | 判定 |
|---|---|
| 节奏 | `page_role` 是否全为「铺垫」，冲突 / 反转 / 爆点是否落位 |
| 机位 | 相邻页 `camera_angle + shot_type` 是否重复 |
| 连续性 | 角色、服装、场景、道具跨页是否一致 |
| 图文一致 | 旁白、`scene`、`action_state`、`image_prompt` 是否同一件事 |
| 章节结尾 | 是否停在悬念、反转或冲突升级处 |
| 封面 / 引导卡 | 文字与本章内容是否匹配 |

输出：章节级摘要 + 逐页问题；可选读取已上传成品图做视觉核对。

## 6. 确定性检查补充

### 6.1 `mapping_check.py`

保留严格覆盖校验，新增**警告**（不阻断）：

- 单段汉字数 > 60；
- 单段汉字数 > 90；
- 单段引号台词或【】消息 > 2 条；
- 单段句末标点 > 5 个；
- 出现多个时间 / 地点转换词；
- 精确拼接失败但归一化拼接通过时，提示「缺失换行 / 标点，不是严格连续」。

### 6.2 `script_check.py`

新增：

- 相邻页 `camera_angle + shot_type` 完全相同；
- `image_prompt` 七段结构是否齐全；
- `characters` 是否都能在角色卡中找到；
- `narration_highlight` 是否为旁白连续片段（已有部分覆盖，补齐逐页）；
- `narration_main` / `narration_sub` 是否逐字出现在 `image_prompt` 的【文字区】；
- 主 / 副旁白是否出现第三人称代词「他 / 她」，出现即拒绝（「其他」「吉他」除外）；
- `page_role` 是否必填且在允许值集合内；
- `camera_angle` 是否必填、非空。

### 6.3 `chapter_check.py`

保持现状，不新增语义判断；章节钩子、标题吸引力由 `storyboard-director` 审。

## 7. 工作流

```mermaid
flowchart LR
    S["story-breakdown<br/>生成"] --> C["检查脚本<br/>硬规则"]
    C --> MD["mapping-director<br/>propose / review"]
    MD --> H["主会话 + 用户确认"]
    H --> W["写回 mapping"]
    W --> P["生成分镜页"]
    P --> NE["narration-editor"]
    NE --> SD["storyboard-director"]
    SD --> F["主会话修复"]
    F --> I["外部生图"]
```

边界约束：

- agent 不写回，主会话是唯一写入口。
- 审片在生图前完成，避免图片返工。
- 检查脚本与 agent 结论冲突时，以脚本的硬规则为准，agent 负责语义解释。
- agent 不替代用户确认。

## 8. 业务不变量

| 编号 | 不变量 |
|---|---|
| CR-01 | agent 不得写回源数据（`mapping` / `pages` / `chapters`）；P0/P1 不写数据库，P2 只允许写 `mapping_reviews` 草稿。 |
| CR-02 | 确定性规则必须由脚本执行，agent 不得用主观判断替代硬规则。 |
| CR-03 | 视觉单元标准只在 SKILL 与本文档定义，agent 提示词必须引用，不得各写一套。 |
| CR-04 | agent 不得改写 `source_text`；只能调整分段边界。 |
| CR-05 | 所有 finding 必须引用具体页码 / 段落与原文证据。 |
| CR-06 | agent 不得编造原文没有的事实、台词、人物或场景。 |
| CR-07 | `mapping-director propose` 必须输出完整候选 mapping；由 `proposal_to_changes.py` 转换为 `MappingReviewChange`，agent 不直接写草稿（P2 除外）。 |
| CR-08 | agent 使用独立上下文；brief 缺少故事 ID / 模式 / 范围时不得开始。 |
| CR-09 | 输出必须区分 `high` / `medium` / `low`，低风险项也不能静默丢弃。 |

## 9. Impacted Files

- `.ai/blueprints/INDEX.md`
- `.claude/agents/mapping-director.md`（新增）
- `.claude/agents/narration-editor.md`（新增，P1）
- `.claude/agents/storyboard-director.md`（新增，P1）
- `.claude/skills/story-breakdown/SKILL.md`
- `.claude/skills/story-breakdown/mapping_check.py`
- `.claude/skills/story-breakdown/script_check.py`
- `.claude/skills/story-breakdown/proposal_to_changes.py`
- `README.md`
- `backend/tests/`（检查脚本回归，可选）

## 10. 实施顺序（三个 agent 都做）

三个内容 agent 都是必做范围；下面只是依赖顺序，不是取舍。

### 第一阶段：规则 + `mapping-director`

- 视觉单元标准写入 `SKILL.md`。
- `mapping_check.py` 增加过载 / 过碎 / 严格连续警告。
- `mapping-director` 的 propose / review 两种模式。
- 用故事 5 验证：propose 覆盖通过，review 能指出过载 / 过碎。

### 第二阶段：`narration-editor` + `storyboard-director`

- `narration-editor`：逐页审主旁白、副旁白、标红、台词、连读。
- `storyboard-director`：逐章审节奏、机位、连续性、图文一致。
- `script_check.py` 增加机位重复、提示词结构、角色引用检查。
- 验证需要已生成的分镜页：优先找现有故事，或在 story 5 的 mapping 确认后生成一章再测。

### 第三阶段：可选增强

- `creative-proposer`：备选钩子 / 标题 / 开场。
- agent 提案直接写入审阅工作台草稿表（仅草稿，不写 `mapping`）。

## 11. 风险与待确认

- **agent 不会凭空更专业**：质量提升来自视觉单元标准；标准不细，换 agent 也没用。
- **过度拆分**：故事 5 从 55 段变成 86 段，需要 review 模式或人工合并；不能把 86 段直接当最终稿。
- **上下文缺失**：独立 agent 不知道聊天里的偏好；brief 必须写清故事 ID、范围、特殊约束。
- **警告误报**：字数、标点阈值只能提示，不能阻断；最终由人或 review 判断。
- **成本**：每章审片都会增加 token；建议 mapping 必跑，旁白 / 审片按章跑。
- **提案契约耦合**：`MappingReviewChange` 以审阅工作台蓝图为准；本蓝图不重复定义字段。

## 12. 变更历史

- **2026-10-27**：建立蓝图草案。确定三层分工、视觉单元标准、三个内容 agent 的职责与只读边界；记录故事 5 的 55 → 86 段实验结论。
- **2026-10-27（补充）**：确认三个内容 agent 均纳入必做范围；按「规则 → mapping-director → narration-editor / storyboard-director」的顺序实施，不做取舍。
- **2026-10-27（实施）**：P0 开始。更新 `SKILL.md` 视觉单元拆分标准；`mapping_check.py` 增加过载 / 过碎 / 严格连续警告；创建 `mapping-director`、`narration-editor`、`storyboard-director` 三个只读 agent 定义；用故事 5 做 mapping-director review 验证。
- **2026-10-27（P0 验证）**：mapping-director review 故事 5 完成。确认 54/54 段边界都落在原文换行处，现有 mapping 是按自然段装箱；脚本补充统计【】消息后，故事 5 高风险段 13 个、警告 25 条。另发现第 3 章正文 16 页已顶满 18 图上限，mapping 拆分前必须先重划章节；修复优先级为 29 → 28 → 24 → 13 → 4。
- **2026-10-27（P1 验证）**：narration-editor + storyboard-director 在故事 3 第 1 章完成验证。`script_check.py` 新增「旁白逐字出现在【文字区】」与「旁白禁用他 / 她代词」两项硬检查；故事 3 第 1 章因此失败：16/16 页副旁白与提示词文字区不一致，9 处代词。审片另发现章末停在铺垫、第 1 章与第 2 章时序倒流，以及 p3 车票、p3/p4 围巾、p7/p13 机位矛盾、p9/p10 重复推门。硬规则原来全过，说明语义 agent 有独立价值。
- **2026-10-27（审阅接入）**：新增 `proposal_to_changes.py`，把 mapping-director 的完整候选 mapping 转成审阅变更；故事 5 的 55 → 86 段提案已验证可转换并应用。
- **2026-10-27（规则同步审计）**：核对 SKILL、蓝图、脚本、agent 四处规则。`mapping_check.py` 与 `mapping_reviews.py` 的阈值和时间转换词完全一致；`script_check.py` 已补齐相邻页机位+景别重复、七段提示词结构、角色卡引用、标红连续片段、`page_role` / `camera_angle` 必填；旁白代词规则补充「其他」「吉他」例外。故事 3 / 4 复跑脚本，只剩已知的代词与文字区问题，无新的误报。
- **2026-10-27（故事 5 第 1 章审片闭环）**：第 1 章 13 页完成两轮独立审片并修订。按建议拆分 18/28 角色变量（我_18/我_28、顾随_18/顾随_28、董思怡_18）；修复 p2 闺蜜身份缺失、p3 撞击画面、p4 年龄与全景、p5/p6/p8/p10/p12 标红重复、p7 机位、p9 时间线、p11 未登记顾随、p12 口吻、p13 语义矛盾与章末钩子；封面主旁白改为「顾随重生了，却选了闺蜜」。`script_check` 与 `chapter_check` 通过，正文 13 页可进入生图；封面/引导卡提示词仍为空。
