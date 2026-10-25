import type {
  ArtStyleOptimizePayload,
  ArtStylesPayload,
  ChapterCoverOptimizePayload,
  ChapterCoverOptimizeResult,
  CharacterOptimizePayload,
  CharacterSyncItem,
  CharacterSyncResult,
  GeneratedCopy,
  Post,
  PostStatus,
  PromptOptimizePayload,
  SettingsData,
  Story,
  StoryboardPage,
  StoryboardPagePayload,
  StoryBreakdown,
  StoryBreakdownPatch,
  StoryChapterPostConfig,
  StoryOptimizationAnalysis,
  StoryPostConfig,
  StoryPostConfigPayload,
  StoryZhihuPayload,
  UploadResult,
  ZhihuAliasSuggestions,
} from '../types'

/** 统一的 API 错误：携带 HTTP 状态码与后端机器错误码。 */
export class ApiError extends Error {
  status: number
  code: string

  constructor(message: string, status: number, code: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export function getErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '操作失败，请稍后重试'
}

interface PostFilters {
  story_id?: number
  status?: PostStatus
}

interface StoryPayload {
  name: string
  content: string
  cover_filename: string | null
  art_style_id: string | null
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData
  let response: Response

  try {
    response = await fetch(path, {
      ...options,
      headers: {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...options.headers,
      },
    })
  } catch {
    throw new ApiError('无法连接服务器，请确认后端已启动', 0, 'NETWORK_ERROR')
  }

  if (response.status === 204) {
    return undefined as T
  }

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(
      data?.detail || '请求失败，请稍后重试',
      response.status,
      data?.code || 'UNKNOWN',
    )
  }
  return data as T
}

export const api = {
  // 设置 / 启动提示词
  getSettings: () => request<SettingsData>('/api/settings'),
  savePrompt: (content: string) =>
    request<SettingsData>('/api/settings/prompt', {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }),
  resetPrompt: () =>
    request<SettingsData>('/api/settings/prompt/reset', { method: 'POST' }),
  saveImagePrefixPrompt: (content: string) =>
    request<SettingsData>('/api/settings/image-prefix-prompt', {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }),
  saveArtStyles: (payload: ArtStylesPayload) =>
    request<SettingsData>('/api/settings/art-styles', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  saveDeepseekKey: (apiKey: string) =>
    request<SettingsData>('/api/settings/deepseek', {
      method: 'PUT',
      body: JSON.stringify({ api_key: apiKey }),
    }),
  clearDeepseekKey: () =>
    request<SettingsData>('/api/settings/deepseek', { method: 'DELETE' }),

  // 故事
  listStories: () => request<Story[]>('/api/stories'),
  createStory: (payload: StoryPayload) =>
    request<Story>('/api/stories', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateStory: (id: number, payload: StoryPayload) =>
    request<Story>(`/api/stories/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  getStory: (id: number) => request<Story>(`/api/stories/${id}`),
  deleteStory: (id: number) =>
    request<void>(`/api/stories/${id}`, { method: 'DELETE' }),
  updateStoryZhihu: (id: number, payload: StoryZhihuPayload) =>
    request<Story>(`/api/stories/${id}/zhihu`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  suggestZhihuAliases: (id: number, title: string) =>
    request<ZhihuAliasSuggestions>(
      `/api/stories/${id}/zhihu/alias-suggestions`,
      {
        method: 'POST',
        body: JSON.stringify({ title }),
      },
    ),

  // 故事拆解结果（由 Claude Code 技能写回，页面可编辑）
  getBreakdown: (storyId: number) =>
    request<StoryBreakdown | null>(`/api/stories/${storyId}/breakdown`),
  patchBreakdown: (storyId: number, payload: StoryBreakdownPatch) =>
    request<StoryBreakdown>(`/api/stories/${storyId}/breakdown`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  /**
   * AI 解读原文到优化文的改动（需要已配置 DeepSeek Key）。
   * 原文与优化文未变时服务端直接返回缓存；force=true 强制重新生成。
   */
  analyzeBreakdown: (storyId: number, force = false) =>
    request<StoryOptimizationAnalysis>(
      `/api/stories/${storyId}/breakdown/analyze${
        force ? '?force=true' : ''
      }`,
      { method: 'POST' },
    ),
  putStoryboardPage: (
    storyId: number,
    pageNumber: number,
    payload: StoryboardPagePayload,
  ) =>
    request<StoryboardPage>(
      `/api/stories/${storyId}/breakdown/pages/${pageNumber}`,
      { method: 'PUT', body: JSON.stringify(payload) },
    ),
  deleteStoryboardPage: (storyId: number, pageNumber: number) =>
    request<void>(`/api/stories/${storyId}/breakdown/pages/${pageNumber}`, {
      method: 'DELETE',
    }),
  /** 上传某页成品图；有图即视为该页完成，重复上传覆盖旧图 */
  uploadStoryboardPageImage: (
    storyId: number,
    pageNumber: number,
    file: File,
  ) => {
    const formData = new FormData()
    formData.append('file', file)
    return request<StoryboardPage>(
      `/api/stories/${storyId}/breakdown/pages/${pageNumber}/image`,
      { method: 'POST', body: formData },
    )
  },
  deleteStoryboardPageImage: (storyId: number, pageNumber: number) =>
    request<void>(
      `/api/stories/${storyId}/breakdown/pages/${pageNumber}/image`,
      { method: 'DELETE' },
    ),
  /** 上传章节封面 / 引导卡；重复上传覆盖旧图 */
  uploadChapterCover: (storyId: number, chapterNumber: number, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return request<StoryBreakdown>(
      `/api/stories/${storyId}/breakdown/chapters/${chapterNumber}/cover/image`,
      { method: 'POST', body: formData },
    )
  },
  deleteChapterCover: (storyId: number, chapterNumber: number) =>
    request<void>(
      `/api/stories/${storyId}/breakdown/chapters/${chapterNumber}/cover/image`,
      { method: 'DELETE' },
    ),
  /** AI 优化章节封面：只返回主标题、副标题、画面提示词三项 */
  optimizeChapterCover: (
    storyId: number,
    chapterNumber: number,
    payload: ChapterCoverOptimizePayload,
  ) =>
    request<ChapterCoverOptimizeResult>(
      `/api/stories/${storyId}/breakdown/chapters/${chapterNumber}/cover/optimize`,
      { method: 'POST', body: JSON.stringify(payload) },
    ),
  uploadChapterGuide: (storyId: number, chapterNumber: number, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return request<StoryBreakdown>(
      `/api/stories/${storyId}/breakdown/chapters/${chapterNumber}/guide/image`,
      { method: 'POST', body: formData },
    )
  },
  deleteChapterGuide: (storyId: number, chapterNumber: number) =>
    request<void>(
      `/api/stories/${storyId}/breakdown/chapters/${chapterNumber}/guide/image`,
      { method: 'DELETE' },
    ),
  /** 导出单章图片（ZIP，按封面 → 正文 → 引导卡排序） */
  chapterExportUrl: (storyId: number, chapterNumber: number) =>
    `/api/stories/${storyId}/breakdown/chapters/${chapterNumber}/export`,
  /** 导出全部章节图片（ZIP，每章一个文件夹） */
  allChaptersExportUrl: (storyId: number) =>
    `/api/stories/${storyId}/breakdown/export-images`,
  /** 给单个角色上传资产图；重复上传覆盖旧图，文件保存在本地 uploads 目录 */
  uploadCharacterAsset: (
    storyId: number,
    characterIndex: number,
    file: File,
  ) => {
    const formData = new FormData()
    formData.append('file', file)
    return request<StoryBreakdown>(
      `/api/stories/${storyId}/breakdown/characters/${characterIndex}/asset-image`,
      { method: 'POST', body: formData },
    )
  },
  deleteCharacterAsset: (storyId: number, characterIndex: number) =>
    request<void>(
      `/api/stories/${storyId}/breakdown/characters/${characterIndex}/asset-image`,
      { method: 'DELETE' },
    ),
  /** 上传最终确认的人物合照；重复上传覆盖旧图，文件保存在本地 uploads 目录 */
  uploadGroupPhoto: (storyId: number, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return request<StoryBreakdown>(
      `/api/stories/${storyId}/breakdown/group-photo`,
      { method: 'POST', body: formData },
    )
  },
  deleteGroupPhoto: (storyId: number) =>
    request<void>(`/api/stories/${storyId}/breakdown/group-photo`, {
      method: 'DELETE',
    }),
  clearStoryboardPages: (storyId: number) =>
    request<void>(`/api/stories/${storyId}/breakdown/pages`, {
      method: 'DELETE',
    }),
  deleteBreakdown: (storyId: number) =>
    request<void>(`/api/stories/${storyId}/breakdown`, { method: 'DELETE' }),

  /**
   * 同步生图平台返回的新版角色卡：按名覆盖外形、追加新角色，
   * 并由后端 AI 联动重写受影响分镜页的「人物回顾」。
   */
  syncCharacters: (storyId: number, characters: CharacterSyncItem[]) =>
    request<CharacterSyncResult>(
      `/api/stories/${storyId}/breakdown/characters/sync`,
      { method: 'POST', body: JSON.stringify({ characters }) },
    ),

  // 每个故事一份的小红书发文配置
  getPostConfig: (storyId: number) =>
    request<StoryPostConfig | null>(
      `/api/stories/${storyId}/post-config`,
    ),
  savePostConfig: (storyId: number, payload: StoryPostConfigPayload) =>
    request<StoryPostConfig>(`/api/stories/${storyId}/post-config`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  getChapterPostConfig: (storyId: number, chapterNumber: number) =>
    request<StoryChapterPostConfig | null>(
      `/api/stories/${storyId}/post-config?chapter=${chapterNumber}`,
    ),
  saveChapterPostConfig: (
    storyId: number,
    chapterNumber: number,
    payload: StoryPostConfigPayload,
  ) =>
    request<StoryChapterPostConfig>(
      `/api/stories/${storyId}/post-config?chapter=${chapterNumber}`,
      {
        method: 'PUT',
        body: JSON.stringify(payload),
      },
    ),

  // 上传
  uploadCover: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return request<UploadResult>('/api/uploads', {
      method: 'POST',
      body: formData,
    })
  },

  // 发文
  listPosts: (filters: PostFilters = {}) => {
    const params = new URLSearchParams()
    if (filters.story_id !== undefined) {
      params.set('story_id', String(filters.story_id))
    }
    if (filters.status !== undefined) {
      params.set('status', filters.status)
    }
    const query = params.toString()
    return request<Post[]>(`/api/posts${query ? `?${query}` : ''}`)
  },
  createPost: (payload: {
    story_id: number
    title: string
    content: string
    status: PostStatus
  }) =>
    request<Post>('/api/posts', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updatePost: (
    id: number,
    payload: { title?: string; content?: string; status?: PostStatus },
  ) =>
    request<Post>(`/api/posts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deletePost: (id: number) =>
    request<void>(`/api/posts/${id}`, { method: 'DELETE' }),
  generateCopy: (storyId: number, chapterNumber?: number) =>
    request<GeneratedCopy>('/api/posts/generate', {
      method: 'POST',
      body: JSON.stringify({
        story_id: storyId,
        ...(chapterNumber !== undefined
          ? { chapter_number: chapterNumber }
          : {}),
      }),
    }),
}

/** 后端 SSE 事件结构。 */
interface PromptOptimizeEvent {
  type: 'delta' | 'done' | 'error'
  content?: string
  message?: string
  code?: string
}

/**
 * 以 SSE 流式获取 AI 优化结果（启动提示词 / 画风描述共用）。
 *
 * 普通请求层只处理 JSON，因此这里单独使用 fetch + ReadableStream。
 * 调用方通过 AbortSignal 取消；错误统一抛 ApiError，便于复用错误提示。
 */
async function* streamOptimization(
  path: string,
  payload:
    | PromptOptimizePayload
    | ArtStyleOptimizePayload
    | CharacterOptimizePayload,
  signal?: AbortSignal,
): AsyncGenerator<string, void, void> {
  let response: Response
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    })
  } catch (error) {
    // 取消请求由调用方识别 AbortError，不转换成业务错误
    if (signal?.aborted) {
      throw error
    }
    throw new ApiError('无法连接服务器，请确认后端已启动', 0, 'NETWORK_ERROR')
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new ApiError(
      data?.detail || '请求失败，请稍后重试',
      response.status,
      data?.code || 'UNKNOWN',
    )
  }

  if (!response.body) {
    throw new ApiError('当前浏览器不支持流式响应', 0, 'STREAM_UNSUPPORTED')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false

  /** 解析一个 SSE 数据块；同一块约定只包含一个事件。 */
  const parseBlock = (block: string): { text?: string; done?: boolean } => {
    for (const line of block.split('\n')) {
      if (!line.startsWith('data:')) continue
      const raw = line.slice('data:'.length).trim()
      if (!raw) continue

      let event: PromptOptimizeEvent
      try {
        event = JSON.parse(raw) as PromptOptimizeEvent
      } catch {
        // 忽略无法解析的片段，避免单个坏包中断整个回答
        continue
      }

      if (event.type === 'delta' && event.content) {
        return { text: event.content }
      }
      if (event.type === 'error') {
        throw new ApiError(
          event.message || 'AI 优化失败，请重试',
          502,
          event.code || 'AI_STREAM_ERROR',
        )
      }
      if (event.type === 'done') {
        return { done: true }
      }
    }
    return {}
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n')

      let separator = buffer.indexOf('\n\n')
      while (separator !== -1) {
        const block = buffer.slice(0, separator)
        buffer = buffer.slice(separator + 2)
        const result = parseBlock(block)
        if (result.text) yield result.text
        if (result.done) {
          finished = true
          return
        }
        separator = buffer.indexOf('\n\n')
      }
    }

    // 处理末尾没有空行分隔的残留事件
    if (buffer.trim()) {
      const result = parseBlock(buffer)
      if (result.text) yield result.text
    }
    finished = true
  } finally {
    if (!finished) {
      // 主动出错或调用方提前退出时，取消底层流以释放连接
      await reader.cancel().catch(() => undefined)
    }
    reader.releaseLock()
  }
}

/** 流式优化启动提示词。 */
export function streamPromptOptimize(
  payload: PromptOptimizePayload,
  signal?: AbortSignal,
): AsyncGenerator<string, void, void> {
  return streamOptimization('/api/settings/prompt/optimize', payload, signal)
}

/** 流式优化画风描述。 */
export function streamArtStyleOptimize(
  payload: ArtStyleOptimizePayload,
  signal?: AbortSignal,
): AsyncGenerator<string, void, void> {
  return streamOptimization('/api/settings/art-styles/optimize', payload, signal)
}

/** 流式优化角色设定卡的外形描述。 */
export function streamCharacterOptimize(
  storyId: number,
  payload: CharacterOptimizePayload,
  signal?: AbortSignal,
): AsyncGenerator<string, void, void> {
  return streamOptimization(
    `/api/stories/${storyId}/breakdown/characters/optimize`,
    payload,
    signal,
  )
}
