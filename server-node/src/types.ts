/** Data types for talk-memory server */

export interface Attachment {
  hash: string;
  name: string;
  size: number;
  mime: string;
}

export interface Message {
  uuid: string;
  parentUuid?: string;
  role: string;
  content: string;
  timestamp: string;
  attachments: Attachment[];
}

export interface Participant {
  name: string;
  role: string;
  model?: string;
}

export interface ConversationMetadata {
  session_id: string;
  platform: string;
  title: string;
  created_at: string;
  updated_at: string;
  participants: Participant[];
  message_count: number;
}

export interface IngestRequest {
  platform: string;
  session_id: string;
  messages: Message[];
  metadata: Record<string, unknown>;
}

export interface ConversationSummary {
  session_id: string;
  platform: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface SearchResult {
  session_id: string;
  platform: string;
  title: string;
  matched_message: string;
  timestamp: string;
}
