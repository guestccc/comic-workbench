export type DeepSeekKeySource = 'env' | 'db' | 'none'

export interface DeepSeekStatus {
  configured: boolean
  source: DeepSeekKeySource
  masked_key: string | null
  db_configured: boolean
}

export interface SettingsData {
  prompt: string
  is_default: boolean
  prompt_updated_at: string | null
  deepseek: DeepSeekStatus
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

export interface Story {
  id: number
  name: string
  content: string
  cover_filename: string | null
  cover_url: string | null
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

export interface UploadResult {
  filename: string
  url: string
}

export interface GeneratedCopy {
  story_id: number
  title: string
  content: string
}
