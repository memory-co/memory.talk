import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { Storage } from '../src/storage';
import { Message } from '../src/types';

describe('Storage', () => {
  let tempDir: string;
  let storage: Storage;

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'talk-memory-'));
    storage = new Storage(tempDir);
  });

  afterEach(() => {
    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  test('saveConversation', () => {
    const messages: Message[] = [
      {
        uuid: 'msg-1',
        role: 'user',
        content: 'Hello',
        timestamp: new Date().toISOString(),
        attachments: [],
      },
      {
        uuid: 'msg-2',
        parentUuid: 'msg-1',
        role: 'assistant',
        content: 'Hi there!',
        timestamp: new Date().toISOString(),
        attachments: [],
      },
    ];

    storage.saveConversation('test', 'sess-1', messages, { title: 'Test Conversation' });

    const result = storage.getConversation('test', 'sess-1');
    expect(result).not.toBeNull();
    expect(result!.metadata.title).toBe('Test Conversation');
    expect(result!.messages.length).toBe(2);
  });

  test('listConversations', () => {
    const messages: Message[] = [
      {
        uuid: 'msg-1',
        role: 'user',
        content: 'Hello',
        timestamp: new Date().toISOString(),
        attachments: [],
      },
    ];

    storage.saveConversation('chatgpt', 'sess-1', messages, { title: 'First' });
    storage.saveConversation('gemini', 'sess-2', messages, { title: 'Second' });

    const allConvs = storage.listConversations();
    expect(allConvs.length).toBe(2);

    const chatgptConvs = storage.listConversations('chatgpt');
    expect(chatgptConvs.length).toBe(1);
    expect(chatgptConvs[0].platform).toBe('chatgpt');
  });

  test('search', () => {
    const messages: Message[] = [
      {
        uuid: 'msg-1',
        role: 'user',
        content: 'How do I deploy to Kubernetes?',
        timestamp: new Date().toISOString(),
        attachments: [],
      },
      {
        uuid: 'msg-2',
        role: 'assistant',
        content: 'You can use kubectl apply -f deployment.yaml',
        timestamp: new Date().toISOString(),
        attachments: [],
      },
    ];

    storage.saveConversation('chatgpt', 'sess-1', messages, { title: 'K8s Deployment' });

    const results = storage.search('kubernetes');
    expect(results.length).toBe(1);
    expect(results[0].matched_message.toLowerCase()).toContain('kubernetes');
  });

  test('saveBlob', () => {
    const data = Buffer.from('Hello, World!');
    const hash = storage.saveBlob('test', data, 'hello.txt');

    const crypto = require('crypto');
    const expectedHash = crypto.createHash('sha256').update(data).digest('hex');
    expect(hash).toBe(expectedHash);
  });
});
