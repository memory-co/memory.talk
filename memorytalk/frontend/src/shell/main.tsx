import React from 'react';
import ReactDOM from 'react-dom/client';
import { AppProviders } from '@/lib/query';
import { Gate } from '@/auth/Gate';
import '@/index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><AppProviders><Gate /></AppProviders></React.StrictMode>,
);
