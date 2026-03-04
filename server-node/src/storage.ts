import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';
import * as yaml from 'yaml';

import {
  ConversationMetadata,
  ConversationSummary,
  Message,
  SearchResult,
} from './types';

export class Storage {
  private basePath: string;
  private conversationsDir: string;
  private blobsDir: string;

  constructor(basePath?: string) {
    this.basePath = basePath || path.join(process.env.HOME || '', '.talk-memory');
    this.conversationsDir = path.join(this.basePath, 'conversations');
    this.blobsDir = path.join(this.basePath, 'blobs');
    this.ensureDirectories();
  }

  private ensureDirectories(): void {
    fs.mkdirSync(this.conversationsDir, { recursive: true });
    fs.mkdirSync(this.blobsDir, { recursive: true });
  }

  private getConversationDir(platform: string, sessionId: string): string {
    return path.join(this.conversationsDir, platform, sessionId);
  }

  saveConversation(
    platform: string,
    sessionId: string,
    messages: Message[],
    metadata: Record<string, unknown>
  ): void {
    const convDir = this.getConversationDir(platform, sessionId);
    fs.mkdirSync(convDir, { recursive: true });

    const metaPath = path.join(convDir, 'meta.yaml');
    const messagesPath = path.join(convDir, 'messages.jsonl');

    const now = new Date().toISOString();
    const title = (metadata.title as string) || `Conversation ${sessionId}`;
    const participants = (metadata.participants as any[]) || [];

    const meta: ConversationMetadata = {
      session_id: sessionId,
      platform,
      title,
      created_at: now,
      updated_at: now,
      participants,
      message_count: messages.length,
    };

    // Save metadata
    fs.writeFileSync(metaPath, yaml.stringify(meta));

    // Load existing messages for deduplication
    const existingUuids = new Set<string>();
    if (fs.existsSync(messagesPath)) {
      const content = fs.readFileSync(messagesPath, 'utf-8');
      for (const line of content.split('\n').filter(Boolean)) {
        const msg = JSON.parse(line);
        existingUuids.add(msg.uuid);
      }
    }

    // Save messages (deduplicate by uuid)
    const file = fs.createWriteStream(messagesPath, { flags: 'a' });
    for (const msg of messages) {
      if (!existingUuids.has(msg.uuid)) {
        file.write(JSON.stringify(msg) + '\n');
        existingUuids.add(msg.uuid);
      }
    }
    file.end();

    // Update message count
    meta.message_count = existingUuids.size;
    fs.writeFileSync(metaPath, yaml.stringify(meta));
  }

  saveBlob(platform: string, fileData: Buffer, filename: string): string {
    const hash = crypto.createHash('sha256').update(fileData).digest('hex');
    const ext = path.extname(filename).slice(1);

    const blobDir = path.join(this.blobsDir, platform, hash.slice(0, 2), hash.slice(2, 4));
    fs.mkdirSync(blobDir, { recursive: true });

    const blobPath = path.join(blobDir, `${hash}.${ext}`);
    if (!fs.existsSync(blobPath)) {
      fs.writeFileSync(blobPath, fileData);
    }

    return hash;
  }

  listConversations(platform?: string): ConversationSummary[] {
    const results: ConversationSummary[] = [];
    const baseDir = platform
      ? path.join(this.conversationsDir, platform)
      : this.conversationsDir;

    if (!fs.existsSync(baseDir)) {
      return results;
    }

    const platformDirs = platform ? [baseDir] : fs.readdirSync(baseDir, { withFileTypes: true })
      .filter(d => d.isDirectory())
      .map(d => path.join(baseDir, d.name));

    for (const platformDir of platformDirs) {
      const platformName = platform || path.basename(platformDir);

      if (!fs.existsSync(platformDir)) continue;

      const sessions = fs.readdirSync(platformDir, { withFileTypes: true })
        .filter(d => d.isDirectory())
        .map(d => path.join(platformDir, d.name));

      for (const sessionDir of sessions) {
        const metaPath = path.join(sessionDir, 'meta.yaml');
        if (!fs.existsSync(metaPath)) continue;

        const metaContent = fs.readFileSync(metaPath, 'utf-8');
        const meta = yaml.parse(metaContent) as ConversationMetadata;

        results.push({
          session_id: meta.session_id,
          platform: meta.platform,
          title: meta.title,
          created_at: meta.created_at,
          updated_at: meta.updated_at,
          message_count: meta.message_count,
        });
      }
    }

    return results.sort((a, b) =>
      new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );
  }

  getConversation(
    platform: string,
    sessionId: string
  ): { metadata: ConversationMetadata; messages: Message[] } | null {
    const convDir = this.getConversationDir(platform, sessionId);
    const metaPath = path.join(convDir, 'meta.yaml');
    const messagesPath = path.join(convDir, 'messages.jsonl');

    if (!fs.existsSync(metaPath)) {
      return null;
    }

    const metaContent = fs.readFileSync(metaPath, 'utf-8');
    const metadata = yaml.parse(metaContent) as ConversationMetadata;

    const messages: Message[] = [];
    if (fs.existsSync(messagesPath)) {
      const content = fs.readFileSync(messagesPath, 'utf-8');
      for (const line of content.split('\n').filter(Boolean)) {
        messages.push(JSON.parse(line));
      }
    }

    return { metadata, messages };
  }

  search(query: string): SearchResult[] {
    const results: SearchResult[] = [];
    const lowerQuery = query.toLowerCase();

    if (!fs.existsSync(this.conversationsDir)) {
      return results;
    }

    const platformDirs = fs.readdirSync(this.conversationsDir, { withFileTypes: true })
      .filter(d => d.isDirectory())
      .map(d => path.join(this.conversationsDir, d.name));

    for (const platformDir of platformDirs) {
      const platform = path.basename(platformDir);

      const sessions = fs.readdirSync(platformDir, { withFileTypes: true })
        .filter(d => d.isDirectory())
        .map(d => path.join(platformDir, d.name));

      for (const sessionDir of sessions) {
        const metaPath = path.join(sessionDir, 'meta.yaml');
        const messagesPath = path.join(sessionDir, 'messages.jsonl');

        if (!fs.existsSync(metaPath)) continue;

        const metaContent = fs.readFileSync(metaPath, 'utf-8');
        const meta = yaml.parse(metaContent) as ConversationMetadata;

        const title = meta.title;
        const sessionId = meta.session_id;

        if (fs.existsSync(messagesPath)) {
          const content = fs.readFileSync(messagesPath, 'utf-8');
          for (const line of content.split('\n').filter(Boolean)) {
            const msg = JSON.parse(line);
            const msgContent = msg.content || '';
            if (msgContent.toLowerCase().includes(lowerQuery)) {
              results.push({
                session_id: sessionId,
                platform,
                title,
                matched_message: msgContent.slice(0, 200),
                timestamp: msg.timestamp,
              });
            }
          }
        }
      }
    }

    return results.sort((a, b) =>
      new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
  }
}
