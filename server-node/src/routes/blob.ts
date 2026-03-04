import { Router, Request, Response } from 'express';
import multer from 'multer';
import { Storage } from '../storage';

const router = Router();
const storage = new Storage();
const upload = multer();

router.post('/api/ingest/blob', upload.single('file'), (req: Request, res: Response) => {
  try {
    const platform = req.body.platform;
    const file = req.file;

    if (!platform || !file) {
      res.status(400).json({ error: 'Missing platform or file' });
      return;
    }

    const hash = storage.saveBlob(platform, file.buffer, file.originalname);

    res.json({ status: 'ok', hash });
  } catch (error) {
    console.error('Error ingesting blob:', error);
    res.status(500).json({ error: 'Failed to ingest blob' });
  }
});

export default router;
