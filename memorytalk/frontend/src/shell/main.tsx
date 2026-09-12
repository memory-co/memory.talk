import React from 'react';
import ReactDOM from 'react-dom/client';
import { AppProviders } from '@/lib/query';
import { Shell } from './Shell';
import '@/index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><AppProviders><Shell /></AppProviders></React.StrictMode>,
);
