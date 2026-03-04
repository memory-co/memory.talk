import express, { Express, Request, Response } from 'express';
import cors from 'cors';
import ingestRoutes from './routes/ingest';
import blobRoutes from './routes/blob';
import { Storage } from './storage';

export function createApp(): Express {
  const app = express();

  // Middleware
  app.use(cors());
  app.use(express.json());

  // Routes
  app.use(ingestRoutes);
  app.use(blobRoutes);

  // Health check
  app.get('/health', (req: Request, res: Response) => {
    res.json({ status: 'ok' });
  });

  // List conversations
  app.get('/api/conversations', (req: Request, res: Response) => {
    try {
      const platform = req.query.platform as string | undefined;
      const storage = new Storage();
      const conversations = storage.listConversations(platform);
      res.json(conversations);
    } catch (error) {
      console.error('Error listing conversations:', error);
      res.status(500).json({ error: 'Failed to list conversations' });
    }
  });

  // Get conversation
  app.get('/api/conversations/:platform/:sessionId', (req: Request, res: Response) => {
    try {
      const { platform, sessionId } = req.params;
      const storage = new Storage();
      const result = storage.getConversation(platform, sessionId);

      if (!result) {
        res.status(404).json({ error: 'Conversation not found' });
        return;
      }

      res.json(result);
    } catch (error) {
      console.error('Error getting conversation:', error);
      res.status(500).json({ error: 'Failed to get conversation' });
    }
  });

  // Search
  app.get('/api/search', (req: Request, res: Response) => {
    try {
      const query = req.query.q as string;
      if (!query) {
        res.status(400).json({ error: 'Missing search query' });
        return;
      }

      const storage = new Storage();
      const results = storage.search(query);
      res.json(results);
    } catch (error) {
      console.error('Error searching:', error);
      res.status(500).json({ error: 'Failed to search' });
    }
  });

  return app;
}
