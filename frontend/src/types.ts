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
  /** 全局生图前置提示词：复制角色卡与分镜提示词时自动拼在开头 */
  image_prefix_prompt: string
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
}

/** 一章一份的小红书文案配置。 */
export interface StoryChapterPostConfig {
  id: number
  story_id: number
  chapter_number: number
  title: string
  content: string
  created_at: string
  updated_at: string
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
