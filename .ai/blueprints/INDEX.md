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
| [2026-10-27-cover-quality-gate.md](2026-10-27-cover-quality-gate.md) | 章节封面点击钩子、3 个变体、封面审片 agent 与硬检查 | 实施中 |
| [2026-10-29-back-to-top.md](2026-10-29-back-to-top.md) | 全站回到顶部入口、滚动目标与阈值 | 已建立 |
| [2026-10-29-image-generation-integration.md](2026-10-29-image-generation-integration.md) | 生图服务配置、角色三视角资产图、封面垫图、生图历史与对比确认 | 实施中 |
| [2026-10-29-collapsible-sider.md](2026-10-29-collapsible-sider.md) | 侧边栏展开 / 收起、宽度、顶栏切换与本地记忆 | 已建立 |
| [2026-10-31-prompt-templates.md](2026-10-31-prompt-templates.md) | 正文 / 封面提示词模板、统一渲染器、设置页编辑与预览 | 实施中 |
| [2026-10-31-story-list-ordering.md](2026-10-31-story-list-ordering.md) | 故事列表按创建时间倒序、编辑不改变位置、前端不二次排序 | 已建立 |
| [2026-10-31-character-copy-with-reference-images.md](2026-10-31-character-copy-with-reference-images.md) | 复制全部角色变量时可选携带角色资产图地址，追加【角色垫图】分块 | 已建立 |
| [2026-10-31-design-feedback-library.md](2026-10-31-design-feedback-library.md) | 小红书 / 手动设计建议库、应用记录、改前改后对比与状态闭环 | 已建立 |
| [2026-10-31-prompt-render-snapshots.md](2026-10-31-prompt-render-snapshots.md) | 提示词渲染快照、封面 / 正文页历史与恢复上一版 | 已建立 |
| [2026-10-31-chapter-asset-history.md](2026-10-31-chapter-asset-history.md) | 章节封面 / 引导卡覆盖前归档、成品图历史与恢复 | 已建立 |
| [2026-11-01-sensitive-word-defaults.md](2026-11-01-sensitive-word-defaults.md) | 小红书 / 抖音商业合规默认词包、缺失回填、载入合并与宽泛词停用 | 已建立 |
| [2026-11-01-settings-tabs.md](2026-11-01-settings-tabs.md) | 设置页四标签、上次标签记忆、切换不丢未保存内容 | 已建立 |
| [2026-11-02-cover-copy-options.md](2026-11-02-cover-copy-options.md) | 封面文案多方案、最强钩子、与发文标题对齐、选后回填再出图 | 已建立 |
| [2026-11-05-character-asset-ingest.md](2026-11-05-character-asset-ingest.md) | 角色资产图 URL / base64 回传接口、替换语义与响应契约 | 已建立 |
| [2026-11-06-background-and-impact-style.md](2026-11-06-background-and-impact-style.md) | 浅米纸底简化背景、1–3 个淡线元素、封面冲击层力度下限、负面词拆分与性别基准 | 实施中 |
| [2026-11-09-multi-platform-publishing.md](2026-11-09-multi-platform-publishing.md) | 抖音 / 小红书、外部 `sau` 子进程、定时 / 立即发布、载荷快照、预览校验、预设标签 | 已实施 |
| [2026-11-10-published-link-capture.md](2026-11-10-published-link-capture.md) | 按需抓取创作中心作品链接、标题匹配、只回填 `external_url`、失败不改状态 | 已实施 |
| [2026-11-10-terminal-launcher.md](2026-11-10-terminal-launcher.md) | 顶栏按钮经后端在项目根目录打开终端并启动 `claude`、回环限制与错误码 | 已实施 |
| [2026-11-10-publish-preflight.md](2026-11-10-publish-preflight.md) | 创建发布任务前的分组检查、别名水印检测、弹窗内修复与同章同账号一次发布门禁 | 已实施 |
| [2026-11-10-platform-icons.md](2026-11-10-platform-icons.md) | 抖音 / 小红书图标资产、`PlatformIcon` / `PlatformLabel` 统一组件与平台标注应用边界 | 已实施 |
| [2026-11-10-xiaohongshu-publish-settings.md](2026-11-10-xiaohongshu-publish-settings.md) | 故事级小红书合集、内容声明选项（含来源转载）、预览检查项、载荷哈希与 CLI 参数传递 | 已实施 |
