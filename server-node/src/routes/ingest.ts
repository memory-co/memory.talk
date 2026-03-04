import { Router, Request, Response } from 'express';
import { Storage } from '../storage';
import { IngestRequest, Message } from '../types';

const router = Router();
const storage = new Storage();

router.post('/api/ingest', (req: Request, res: Response) => {
  try {
    const body = req.body as IngestRequest;

    // Convert messages to proper format
    const messages: Message[] = body.messages.map(msg => ({
      uuid: msg.uuid,
      parentUuid: msg.parentUuid,
      role: msg.role,
      content: msg.content,
      timestamp: msg.timestamp,
      attachments: msg.attachments || [],
    }));

    storage.saveConversation(
      body.platform,
      body.session_id,
      messages,
      body.metadata
    );

    res.json({ status: 'ok', session_id: body.session_id });
  } catch (error) {
    console.error('Error ingesting conversation:', error);
    res.status(500).json({ error: 'Failed to ingest conversation' });
  }
});

export default router;
