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

export interface SettingsData {
  prompt: string
  is_default: boolean
  prompt_updated_at: string | null
  deepseek: DeepSeekStatus
  art_styles: ArtStyle[]
  active_art_style: string | null
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
}

/** 单页分镜，对应工作台详情页「分镜头脚本」中的一页。 */
export interface StoryboardPage {
  page_number: number
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
  image_prompt: string
}

export type StoryboardPagePayload = Omit<StoryboardPage, 'page_number'>

/** 故事拆解结果：优化后文章、角色卡与分镜页。 */
export interface StoryBreakdown {
  id: number
  story_id: number
  optimized_content: string
  characters: CharacterCard[]
  /** @deprecated 新流程不再生成人物合影提示词；字段保留以兼容旧数据。 */
  group_photo_prompt: string
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
}

export interface UploadResult {
  filename: string
  url: string
}

export interface GeneratedCopy {
  story_id: number
  title: string
  content: string
}
