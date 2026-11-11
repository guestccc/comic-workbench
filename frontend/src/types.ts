export type DeepSeekKeySource = 'env' | 'db' | 'none'

export interface DeepSeekStatus {
  configured: boolean
  source: DeepSeekKeySource
  masked_key: string | null
  db_configured: boolean
}

export interface ArtStyle {
  id: string
  name: string
  content: string
}

export interface ArtStylesPayload {
  styles: ArtStyle[]
  active_id: string | null
}

export interface ImageProviderStatus {
  configured: boolean
  source: 'env' | 'db' | 'none'
  masked_key: string | null
  base_url: string
  model: string
  size: string
  quality: string
  db_configured: boolean
}

export interface ImageProviderPayload {
  base_url: string
  model: string
  size: string
  quality: 'auto' | 'low' | 'medium' | 'high'
  api_key?: string
}

export interface ImageProviderTestResult {
  ok: boolean
  models: string[]
  message: string
}

export interface SettingsData {
  prompt: string
  is_default: boolean
  prompt_updated_at: string | null
  deepseek: DeepSeekStatus
  art_styles: ArtStyle[]
  active_art_style: string | null
  /** 全局生图前置提示词：复制角色卡与分镜提示词时自动拼在开头 */
  image_prefix_prompt: string
  image_provider: ImageProviderStatus
}

export type ImageGenerationTarget =
  | 'character_asset'
  | 'chapter_cover'
  | 'chapter_guide'
  | 'page'

export interface ImageGenerationPreview {
  generation_id: string
  target_type: ImageGenerationTarget
  old_url: string | null
  new_url: string
  model: string
  size: string
  elapsed_ms: number
}

export interface ImageGenerationItem {
  id: string
  target_type: ImageGenerationTarget
  url: string
  created_at: string
  model: string
  size: string
  file_bytes: number
  used_at: string | null
  is_current: boolean
  /** 本次实际发给上游生图 API 的完整提示词 */
  prompt: string
  /** 本次使用的角色参考图名称 */
  reference_names: string[]
}

export interface ImageGenerationList {
  items: ImageGenerationItem[]
  total_bytes: number
}

export type AliasStampTarget = 'page' | 'cover' | 'guide'

export interface AliasStampItem {
  target: AliasStampTarget
  chapter_number: number | null
  page_number: number | null
  ok: boolean
  error: string | null
}

export interface AliasStampResult {
  alias: string
  stamped: number
  failed: number
  items: AliasStampItem[]
  backup_dir: string
}

export interface AliasRestoreResult {
  restored: number
  failed: number
  items: AliasStampItem[]
}

export interface ImageGenerationClearResult {
  deleted: number
  freed_bytes: number
}

export interface PromptTemplatesData {
  body: string
  cover: string
  body_default: string
  cover_default: string
  body_is_default: boolean
  cover_is_default: boolean
  placeholders: string[]
}

export interface PromptTemplatesPayload {
  body: string
  cover: string
}

export interface PromptTemplateVersion {
  id: number
  template_type: 'body' | 'cover'
  content: string
  note: string
  created_at: string
}

export interface PromptRenderPayload {
  template_type: 'body' | 'cover'
  story_id: number
  preview?: boolean
  context: {
    content: string
    character_consistency: string
    narration_main: string
    narration_sub: string
    narration_highlight: string
    dialogues: string[]
    page_number?: number | null
    chapter_number?: number | null
    label?: string
  }
}

export interface AppliedDesignRule {
  id: number
  title: string
  kind: DesignRuleKind
  target: DesignRuleTarget
  scope_type: DesignRuleScopeType
  priority: DesignRulePriority
  requirement: string
  negative_terms: string[]
  review_check: string
}

export interface RuleCheckResult {
  rule_id: number
  title: string
  passed: boolean
  message: string
}

export interface PromptRenderResult {
  prompt: string
  template_type: 'body' | 'cover'
  story_id: number
  applied_rules: AppliedDesignRule[]
  rule_checks: RuleCheckResult[]
  snapshot_id: number | null
}

export interface PromptSnapshot {
  id: number
  story_id: number
  target_type: 'cover' | 'body'
  chapter_number: number | null
  page_number: number | null
  template_type: 'body' | 'cover'
  prompt: string
  applied_rules: AppliedDesignRule[]
  rule_checks: RuleCheckResult[]
  restored_from_id: number | null
  created_at: string
}

export interface PromptSnapshotRestoreResult {
  snapshot: PromptSnapshot
  target_type: 'cover' | 'body'
  chapter_number: number | null
  page_number: number | null
}

export type PromptOptimizeRole = 'user' | 'assistant'

export interface PromptOptimizeMessage {
  role: PromptOptimizeRole
  content: string
}

export interface PromptOptimizePayload {
  current_prompt: string
  messages: PromptOptimizeMessage[]
}

export interface ArtStyleOptimizePayload {
  current_style: string
  messages: PromptOptimizeMessage[]
}

/** AI 优化角色外形描述的请求；姓名与身份仅作上下文。 */
export interface CharacterOptimizePayload {
  character_name: string
  character_role: string
  current_appearance: string
  messages: PromptOptimizeMessage[]
}

/** AI 优化章节封面：只允许改主标题、副标题与画面提示词。 */
export interface ChapterCoverOptimizePayload {
  chapter_title: string
  cover_label: string
  cover_main: string
  cover_sub: string
  cover_highlight: string
  current_prompt: string
  suggestion: string
}

export interface ChapterCoverOptimizeResult {
  narration_main: string
  narration_sub: string
  image_prompt: string
}

/** 生成封面文案方案的请求；可带当前未保存的封面文字与用户方向。 */
export interface CoverCopyOptionsPayload {
  chapter_title: string
  cover_label: string
  cover_main: string
  cover_highlight: string
  cover_sub: string
  direction?: string
}

/** 单个封面文案方案：主标题、标红词、副标题与画面建议。 */
export interface CoverCopyOption {
  style: string
  feature: string
  hook_source: string
  visual_hint: string
  visual_content: string
  narration_main: string
  narration_highlight: string
  narration_sub: string
  recommended: boolean
  recommend_reason: string
  image_prompt: string
}

export interface CoverCopyOptionsResponse {
  story_id: number
  chapter_number: number
  post_title: string | null
  options: CoverCopyOption[]
}

/** 从生图平台同步回来的单个角色：名字用于匹配，外形整体覆盖。 */
export interface CharacterSyncItem {
  name: string
  appearance: string
}

/** 角色卡同步结果摘要。 */
export interface CharacterSyncResult {
  /** 按名匹配后更新了外形的角色 */
  updated_names: string[]
  /** 平台返回了但工作台还没有的新角色 */
  created_names: string[]
  /** 人物回顾被 AI 重写的分镜页页码 */
  review_updated_pages: number[]
  /** 未配置 Key 或没有受影响页面时跳过人物回顾同步的原因 */
  review_warning: string | null
}

export interface SensitiveWord {
  word: string
  replacement: string
  category: string
  enabled: boolean
}

export interface SensitiveWordMatch {
  word: string
  replacement: string
  category: string
  start: number
  end: number
}

export interface SensitiveScanResult {
  matches: SensitiveWordMatch[]
  total: number
  counts: Record<string, number>
  dictionary_version: string
}

export interface SensitiveApplyItem {
  word: string
  replacement: string
}

export interface SensitiveAppliedItem extends SensitiveApplyItem {
  count: number
}

export interface SensitiveEdit {
  original_content: string
  result_content: string
  items: SensitiveAppliedItem[]
  applied_at: string
  dictionary_version: string
}

export interface SensitiveApplyResult {
  content: string
  items: SensitiveAppliedItem[]
  dictionary_version: string
  sensitive_edit: SensitiveEdit
}

export interface Story {
  id: number
  name: string
  content: string
  cover_filename: string | null
  cover_url: string | null
  /** 该故事选用的画风 id；为空表示未选择 */
  art_style_id: string | null
  /** 后端解析出的画风名称/描述；画风已删除时均为 null */
  art_style_name: string | null
  art_style_content: string | null
  /** 知乎推广信息：原文 ID / 在知乎注册的搜索别名；原名标题即故事名 */
  zhihu_article_id: string
  zhihu_alias: string
  /** 候选别名；zhihu_alias 是最终使用并写进正文的那一个 */
  zhihu_aliases: string[]
  /** 敏感词替换审计；没有执行过时为空 */
  sensitive_edit?: SensitiveEdit | null
  /** 小红书发布设置（故事级）：合集名、内容声明与来源媒体名 */
  xhs_collection: string
  /** 平台固定文案之一；空串表示不声明 */
  xhs_declaration: string
  /** 仅「来源转载」声明下生效 */
  xhs_repost_source: string
  created_at: string
  updated_at: string
}

export type PostStatus = 'draft' | 'published'

export interface Post {
  id: number
  story_id: number
  story_name: string
  title: string
  content: string
  status: PostStatus
  created_at: string
  updated_at: string
}

/** 分镜页景别，与后端 Literal 保持一致。 */
export type StoryboardShotType = '全景' | '中景' | '特写'

/** 角色设定卡：一段外形描述覆盖发型、长相、年龄、服装、配饰与体态。 */
export interface CharacterCard {
  name: string
  role: string
  appearance: string
  /** 角色资产图文件名；服务端生成，与角色名解耦 */
  asset_filename?: string | null
  /** 角色资产图访问地址；由服务端按文件是否存在计算 */
  asset_url?: string | null
}

/** 单页分镜，对应工作台详情页「分镜头脚本」中的一页。 */
export interface StoryboardPage {
  /** 脚本页码：成片顺序，从 1 连续编号 */
  page_number: number
  /** 来源对照段号；未选中的对照段不生成，也不占脚本页码。旧数据可能为空 */
  mapping_page_number: number | null
  /** 所属章节；未启用章节的旧数据为空 */
  chapter_number: number | null
  /** 章内页码：图片里显示的「第X页」以此为准 */
  chapter_page_number: number | null
  /** 服务端计算的展示页码：chapter_page_number ?? page_number */
  display_page_number?: number | null
  is_flashback: boolean
  /** 本页在故事中的作用：钩子封面 / 铺垫 / 冲突 / 反转 / 爆点 / 情绪高潮 / 收尾 */
  page_role: string
  story_content: string
  characters: string[]
  character_review: string
  scene: string
  action_state: string
  change_note: string
  narration_main: string
  narration_highlight: string
  narration_sub: string
  dialogues: string[]
  shot_type: StoryboardShotType
  /** 机位方位：正面 / 45°侧面 / 正侧面 / 背面 / 过肩视角 / 俯视 / 仰视 / 主观视角 等 */
  camera_angle: string
  image_prompt: string
  /** 成品图地址；有图即视为该页已完成（服务端按文件是否存在计算） */
  image_url: string | null
}

export type StoryboardPagePayload = Omit<
  StoryboardPage,
  | 'page_number'
  | 'display_page_number'
  | 'mapping_page_number'
  | 'chapter_number'
  | 'chapter_page_number'
  | 'image_url'
> & {
  /** 编辑已有页时可省略，后端会沿用原关联 */
  mapping_page_number?: number | null
  chapter_number?: number | null
  chapter_page_number?: number | null
}

/** 分镜对照表的一行：第几页对应优化文的哪一段。 */
export interface StoryboardMappingItem {
  page_number: number
  /** 该页对应的优化文原文摘录，按原文顺序连续 */
  source_text: string
  /** 给对照表看的一句话简述，不是最终副旁白 */
  summary: string
  /** 例如「第3段」 */
  paragraph: string
  /** 例如「1/2」，表示该段被拆成的第几部分 */
  part: string
  /** 已弃用：保留以维持全文覆盖，但不分入任何章节 */
  excluded: boolean
}

/** 章节封面：顶部小字 + 主旁白 + 副旁白 + 生图提示词。 */
export interface ChapterCover {
  label: string
  narration_main: string
  narration_highlight: string
  narration_sub: string
  image_prompt: string
}

export interface ChapterAssetArchive {
  filename: string
  url: string
  bytes: number
  created_at: string
}

export interface ChapterCoverRead extends ChapterCover {
  image_url: string | null
}

/** 章节末尾引导卡：主文案 + 下一章预告 / 主页简介引导。 */
export interface ChapterGuide {
  text: string
  sub_text: string
  image_prompt: string
}

export interface ChapterGuideRead extends ChapterGuide {
  image_url: string | null
}

/** 一章 = 一篇小红书笔记：1 封面 + 1..16 正文档 + 1 引导卡。 */
export interface StoryboardChapter {
  chapter_number: number
  title: string
  mapping_page_numbers: number[]
  cover: ChapterCover
  guide: ChapterGuide
}

export interface StoryboardChapterRead extends StoryboardChapter {
  cover: ChapterCoverRead
  guide: ChapterGuideRead
}

/** 故事拆解结果：优化后文章、角色卡与分镜页。 */
export interface StoryBreakdown {
  id: number
  story_id: number
  optimized_content: string
  characters: CharacterCard[]
  /** @deprecated 新流程不再生成人物合影提示词；字段保留以兼容旧数据。 */
  group_photo_prompt: string
  /** 最终确认的人物合照地址；由服务端按文件是否存在计算 */
  group_photo_url: string | null
  /** 分镜对照表：第一步只写这张表，第二步据此生成分镜页 */
  mapping: StoryboardMappingItem[]
  /** 章节发布分组；空数组表示未启用章节 */
  chapters: StoryboardChapterRead[]
  pages: StoryboardPage[]
  art_style_id: string | null
  art_style_name: string | null
  art_style_content: string | null
  /** 原文已修改 / 画风已变更，由后端计算 */
  is_content_stale: boolean
  is_art_style_stale: boolean
  created_at: string
  updated_at: string
}

/** 分镜对照审阅：一条拆分 / 合并 / 保留提案。 */
export type MappingChangeKind = 'split' | 'merge' | 'keep'
export type MappingRisk = 'high' | 'medium' | 'low'
export type MappingDecision = 'approved' | 'rejected' | 'undecided'

export interface ProposedMappingSegment {
  source_text: string
  summary: string
  paragraph: string
  part: string
  beat_type: string
  time_place: string
  characters: string[]
  visual_load: number | null
}

export interface MappingReviewChange {
  id: string
  kind: MappingChangeKind
  risk: MappingRisk
  old_page_numbers: number[]
  proposed_segments: ProposedMappingSegment[]
  reason: string
  page_delta: number
  crosses_chapter: boolean
}

export interface MappingReviewSummary {
  current_page_count: number
  proposed_page_count: number
  total_changes: number
  pending_count: number
  auto_approved_count: number
  rejected_count: number
  chapters_count: number
  chapters_locked: boolean
}

export interface MappingReview {
  id: number
  story_id: number
  status: 'draft' | 'applied' | 'discarded'
  base_mapping_hash: string
  changes: MappingReviewChange[]
  decisions: Record<string, MappingDecision>
  summary: MappingReviewSummary
  created_at: string
  updated_at: string
  applied_at: string | null
}

export interface MappingReviewApplyResult {
  breakdown: StoryBreakdown
  strict_coverage: boolean
  chapters_cleared: boolean
}

/** AI 对原文 → 优化文单处改动的解读。 */
export interface OptimizationChangeNote {
  /** 改动类型：钩子 / 悬念 / 信息差 / 爆点 / 节奏 / 情绪 / 口语化 / 细节 / 删减 / 保留 */
  kind: string
  /** 原文中的对应句子；纯新增时为空字符串 */
  original: string
  /** 优化后的对应句子；纯删除时为空字符串 */
  optimized: string
  /** 为什么这样改，对读者有什么作用 */
  why: string
}

/** 原文与优化文的 AI 解读结果。 */
export interface StoryOptimizationAnalysis {
  summary: string
  changes: OptimizationChangeNote[]
}

/** 拆解头部信息的局部更新，未传字段保持不变。 */
export interface StoryBreakdownPatch {
  optimized_content?: string
  characters?: CharacterCard[]
  /** 分镜对照表；第一步只写表，不写分镜页 */
  mapping?: StoryboardMappingItem[]
  /** 章节发布分组；必须按对照表顺序覆盖全部未弃用段 */
  chapters?: StoryboardChapter[]
  /** @deprecated 新流程不再写入；保留以兼容旧数据与接口。 */
  group_photo_prompt?: string
}

/** 每个故事一份的小红书发文配置。 */
export interface StoryPostConfig {
  id: number
  story_id: number
  title: string
  content: string
  created_at: string
  updated_at: string
}

export interface StoryPostConfigPayload {
  title: string
  content: string
  tags?: string[]
}

/** 一章一份的小红书文案配置。 */
export interface StoryChapterPostConfig {
  id: number
  story_id: number
  chapter_number: number
  title: string
  content: string
  /** 本章选中的发布标签；预设标签只是候选项 */
  tags: string[]
  created_at: string
  updated_at: string
}

// ---------------------------------------------------------------------------
// 多平台发布（抖音 / 小红书）
// ---------------------------------------------------------------------------

// 多平台发布（抖音 / 小红书）
export type PublishPlatform = 'douyin' | 'xiaohongshu'
export type PublishMode = 'scheduled' | 'immediate'
export type PublishJobStatus =
  | 'queued'
  | 'running'
  | 'scheduled'
  | 'failed'
  | 'unknown'
  | 'published'
export type PublishAccountStatus = 'unknown' | 'valid' | 'invalid'

export interface PublishTagPresets {
  tags: string[]
}

/** 小红书内容声明可选项；由后端给出，前端只渲染 */
export interface XhsDeclarationOptions {
  options: { value: string; label: string }[]
  default: string
  /** 需要额外填写来源媒体名的选项值 */
  repost_value: string
}

export interface PublishAccount {
  id: number
  platform: PublishPlatform
  account_name: string
  display_name: string
  status: PublishAccountStatus
  last_checked_at: string | null
  created_at: string
  updated_at: string
}

export interface PublishImage {
  label: string
  url: string
  filename: string
}

export interface PublishPreviewPayload {
  story_id: number
  chapter_number: number
  platform: PublishPlatform
  account_id: number
  publish_mode: PublishMode
  schedule_at: string | null
}

export type PreflightStatus = 'pass' | 'warning' | 'error'

export type PreflightGroup =
  | 'content'
  | 'alias'
  | 'images'
  | 'account'
  | 'platform'

export type PreflightAction =
  | 'stamp_alias'
  | 'check_login'
  | 'open_zhihu'
  | 'open_chapters'
  | 'open_post_config'

export interface PreflightCheckItem {
  label: string
  status: PreflightStatus
}

export interface PreflightCheck {
  key: string
  group: PreflightGroup
  label: string
  status: PreflightStatus
  message: string
  action: PreflightAction | null
  action_label: string | null
  items: PreflightCheckItem[]
}

export interface PublishPreview {
  platform: PublishPlatform
  publish_mode: PublishMode
  account: PublishAccount
  title: string
  note: string
  tags: string[]
  images: PublishImage[]
  image_count: number
  title_length: number
  note_length: number
  schedule_at: string | null
  schedule_min_at: string
  schedule_max_at: string
  payload_hash: string | null
  source_hash: string | null
  /** 小红书发布设置：声明文案、来源媒体名与合集名；抖音为空 */
  declaration: string | null
  repost_source: string | null
  collection: string | null
  checks: PreflightCheck[]
  errors: string[]
  warnings: string[]
}

export interface PublishJobCreatePayload extends PublishPreviewPayload {
  preview_hash: string
  confirm: boolean
}

export interface PublishPayload {
  platform: string
  mode: PublishMode
  account_name: string
  title: string
  note: string
  tags: string[]
  images: string[]
  schedule_at: string | null
  /** 小红书发布设置；历史任务没有这几项 */
  declaration: string | null
  repost_source: string | null
  collection: string | null
}

export interface PublishJob {
  id: string
  story_id: number
  chapter_number: number
  platform: PublishPlatform
  account_id: number
  status: PublishJobStatus
  scheduled_at: string
  payload: PublishPayload
  payload_hash: string
  source_hash: string
  snapshot_dir: string
  external_url: string
  exit_code: number | null
  stdout_excerpt: string
  error_message: string
  started_at: string | null
  finished_at: string | null
  log_available: boolean
  created_at: string
  updated_at: string
}

export interface PublishJobLog {
  job_id: string
  text: string
  truncated: boolean
}

export interface PublishJobPatchPayload {
  status?: 'scheduled' | 'failed' | 'published'
  external_url?: string
}

/** 更新故事级知乎推广信息；原名标题直接使用故事名，不单独提交。 */
export interface StoryZhihuPayload {
  zhihu_article_id: string
  zhihu_alias: string
  zhihu_aliases: string[]
}

export interface ZhihuAliasSuggestions {
  aliases: string[]
}

export interface UploadResult {
  filename: string
  url: string
}

/** AI 生成的一个可选文案方案：方案名 + 特点 + 标题正文。 */
export interface GeneratedCopyOption {
  style: string
  feature: string
  title: string
  content: string
  recommended: boolean
  recommend_reason: string
}

export interface GeneratedCopy {
  story_id: number
  chapter_number?: number | null
  options: GeneratedCopyOption[]
}

export type DesignFeedbackSource = 'xiaohongshu' | 'manual'
export type DesignFeedbackCategory =
  | 'cover'
  | 'comic'
  | 'title'
  | 'color'
  | 'expression'
  | 'text'
  | 'pacing'
  | 'other'
export type DesignFeedbackScope = 'global' | 'story' | 'chapter'
export type DesignFeedbackPriority = 'low' | 'medium' | 'high'
export type DesignFeedbackStatus = 'open' | 'applied' | 'verified' | 'archived'
export type DesignFeedbackRuleTarget = 'cover' | 'comic' | 'all'
export type DesignFeedbackTargetType =
  | 'cover'
  | 'page'
  | 'guide'
  | 'character'
  | 'other'

/** 一次建议应用：记录目标与改前 / 改后快照。 */
export interface DesignFeedbackApplication {
  id: number
  feedback_id: number
  target_type: DesignFeedbackTargetType
  story_id: number
  story_name: string | null
  chapter_number: number | null
  page_number: number | null
  summary: string
  before_prompt: string | null
  after_prompt: string | null
  before_image_url: string | null
  after_image_url: string | null
  applied_at: string
}

/** 小红书 / 手动设计建议；详情额外带应用记录。 */
export interface DesignFeedback {
  id: number
  title: string
  content: string
  source: DesignFeedbackSource
  source_url: string
  screenshot_filename: string | null
  screenshot_url: string | null
  category: DesignFeedbackCategory
  scope: DesignFeedbackScope
  story_id: number | null
  story_name: string | null
  chapter_number: number | null
  tags: string[]
  priority: DesignFeedbackPriority
  status: DesignFeedbackStatus
  application_count: number
  is_rule: boolean
  rule_text: string
  rule_target: DesignFeedbackRuleTarget
  rule_promoted_at: string | null
  created_at: string
  updated_at: string
}

export interface DesignFeedbackDetail extends DesignFeedback {
  applications: DesignFeedbackApplication[]
}

export interface DesignFeedbackPayload {
  title: string
  content: string
  source: DesignFeedbackSource
  source_url: string
  screenshot_filename: string | null
  category: DesignFeedbackCategory
  scope: DesignFeedbackScope
  story_id: number | null
  chapter_number: number | null
  tags: string[]
  priority: DesignFeedbackPriority
}

export interface DesignFeedbackUpdatePayload
  extends Partial<DesignFeedbackPayload> {
  status?: DesignFeedbackStatus
}

export interface DesignFeedbackRulePromotePayload {
  rule_text: string
  rule_target: DesignFeedbackRuleTarget
}

export type DesignRuleKind = 'prompt' | 'negative' | 'text' | 'review' | 'check'
export type DesignRuleTarget = 'cover' | 'body' | 'guide' | 'all'
export type DesignRuleSlot = 'scene' | 'cover_mode' | 'text_zone' | 'none'
export type DesignRuleScopeType = 'global' | 'story' | 'chapter' | 'pages'
export type DesignRulePriority = 'hard' | 'soft'
export type DesignRuleStatus = 'draft' | 'active' | 'disabled'
export type DesignRuleCreatedBy = 'claude' | 'user'

export interface DesignRule {
  id: number
  feedback_id: number
  feedback_title: string | null
  title: string
  kind: DesignRuleKind
  target: DesignRuleTarget
  slot: DesignRuleSlot
  scope_type: DesignRuleScopeType
  story_id: number | null
  story_name: string | null
  chapter_numbers: number[]
  page_numbers: number[]
  priority: DesignRulePriority
  requirement: string
  negative_terms: string[]
  review_check: string
  check_spec: Record<string, unknown>
  status: DesignRuleStatus
  version: number
  created_by: DesignRuleCreatedBy
  check_count: number
  passed_count: number
  failed_count: number
  latest_result: string | null
  template_applied_at: string | null
  coverage_run_id: number | null
  coverage_status: string | null
  coverage_total: number
  coverage_pending: number
  coverage_updated_at: string | null
  created_at: string
  updated_at: string
}

export interface DesignRulePayload {
  title: string
  kind: DesignRuleKind
  target: DesignRuleTarget
  slot: DesignRuleSlot
  scope_type: DesignRuleScopeType
  story_id: number | null
  chapter_numbers: number[]
  page_numbers: number[]
  priority: DesignRulePriority
  requirement: string
  negative_terms: string[]
  review_check: string
  check_spec: Record<string, unknown>
  created_by?: DesignRuleCreatedBy
}

export interface DesignRuleUpdatePayload
  extends Partial<DesignRulePayload> {}

export interface DesignRuleResult {
  id: number
  rule_id: number
  story_id: number
  target_type: 'cover' | 'body' | 'guide' | 'other'
  chapter_number: number | null
  page_number: number | null
  result: 'passed' | 'failed' | 'unknown'
  message: string
  image_url: string | null
  snapshot_id: number | null
  reviewer: 'claude' | 'user'
  created_at: string
}

export interface DesignRuleOnceTarget {
  target_type: 'cover' | 'body'
  story_id: number
  chapter_number: number
  page_number?: number | null
}

export interface DesignRuleOncePreview {
  target_type: 'cover' | 'body'
  story_id: number
  chapter_number: number
  page_number: number | null
  before: string
  after: string
  inserted_block: string
}

export interface DesignRuleOnceApplyResult {
  rule: DesignRule
  target_type: 'cover' | 'body'
  story_id: number
  chapter_number: number
  page_number: number | null
  prompt: string
}

export interface DesignRuleTemplatePreviewItem {
  template_type: 'body' | 'cover'
  before: string
  after: string
  inserted_block: string
}

export interface DesignRuleTemplatePreview {
  items: DesignRuleTemplatePreviewItem[]
}

export interface DesignRuleTemplateApplyResult {
  templates: PromptTemplatesData
  rule: DesignRule
  applied_template_types: ('body' | 'cover')[]
}

export interface DesignRulePreviewPayload {
  target: DesignRuleTarget
  scope_type: DesignRuleScopeType
  story_id?: number | null
  chapter_numbers: number[]
  page_numbers: number[]
}

export interface DesignRulePreviewResult {
  cover: number
  body: number
  guide: number
  total: number
  samples: string[]
}

export interface DesignFeedbackApplicationPayload {
  target_type: DesignFeedbackTargetType
  story_id: number
  chapter_number?: number | null
  page_number?: number | null
  summary: string
  before_prompt?: string | null
  after_prompt?: string | null
  before_image_url?: string | null
  after_image_url?: string | null
}

export interface DesignRuleCoverageItem {
  item_key: string
  story_id: number
  story_name: string
  target_type: 'cover' | 'body' | 'guide'
  chapter_number: number
  page_number: number | null
  chapter_title: string
  prompt: string
  prompt_hash: string
  deterministic: Record<string, unknown>
  ai_status: 'pending' | 'covered' | 'partial' | 'missing' | 'not_applicable' | 'not_generated' | 'error'
  ai_confidence: number
  ai_evidence: string[]
  ai_missing: string[]
  ai_suggested_fix: string
  ai_reason: string
  confirm_status: 'pending' | 'confirmed'
  confirmed_at: string | null
  confirmation_note: string
  final_status: string
}

export interface DesignRuleCoverageRun {
  id: number
  rule_id: number
  feedback_id: number
  rule_version: number
  scope_snapshot: Record<string, unknown>
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled' | 'interrupted'
  total: number
  processed: number
  covered: number
  partial: number
  missing: number
  pending: number
  error_count: number
  items: DesignRuleCoverageItem[]
  error_message: string
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface TerminalLaunchResult {
  terminal: string
  directory: string
  message: string
}
