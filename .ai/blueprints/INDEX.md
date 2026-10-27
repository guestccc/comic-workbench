# 蓝图索引

> 蓝图是架构边界、公共契约、数据流和关键行为的事实源。修改相关代码前先读对应蓝图；契约变化时先更新蓝图。

| 蓝图 | 范围 | 状态 |
|---|---|---|
| [2026-10-24-story-data-model-and-numbering.md](2026-10-24-story-data-model-and-numbering.md) | Story / Mapping / Chapter / Page 关系、三种页码、章节覆盖、页面归属与不变量 | 已建立 |
| [2026-10-24-prompt-contract-and-rendering.md](2026-10-24-prompt-contract-and-rendering.md) | 结构化字段 → `image_prompt` 的唯一渲染规则；展示、复制、导出、封面/引导卡文字契约 | 已建立 |
| [2026-10-24-chapter-publishing-and-assets.md](2026-10-24-chapter-publishing-and-assets.md) | 封面 / 正文 / 引导卡顺序、图片路径、ZIP 导出、单章 18 张上限 | 已建立 |
| [2026-10-24-zhihu-alias-and-post-config.md](2026-10-24-zhihu-alias-and-post-config.md) | 候选别名、最终别名、正文前缀同步、按章发文配置 | 已建立 |
| [2026-10-24-ai-generation-and-writeback.md](2026-10-24-ai-generation-and-writeback.md) | Claude / DeepSeek 输出的 Schema、写回边界、校验与失败处理 | 已建立 |
| [2026-10-24-integrity-and-delivery.md](2026-10-24-integrity-and-delivery.md) | 全部业务不变量、审计入口、测试矩阵、交付检查清单 | 已建立 |
| [2026-10-24-multi-page-prompt-copy.md](2026-10-24-multi-page-prompt-copy.md) | 分镜页多选、整章全选、批量复制顺序与跨章标签 | 已建立 |
| [2026-10-27-mapping-review-workbench.md](2026-10-27-mapping-review-workbench.md) | 分镜对照提案草稿、人工决策队列、服务端应用、页码重排与章节安全闸门 | 实施中 |
| [2026-10-27-content-review-agents.md](2026-10-27-content-review-agents.md) | 内容审阅 agent、视觉单元拆分标准、旁白 / 分镜审片与检查脚本补充 | 实施中 |
