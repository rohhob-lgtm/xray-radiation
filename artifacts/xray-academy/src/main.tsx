import { createRoot } from 'react-dom/client';

import App from './App';

import './index.css';

createRoot(document.getElementById('root')!).render(<App />);

// Register the PWA service worker (installable + offline app shell). Done here
// in bundled code so it satisfies the strict CSP (script-src 'self'); an inline
// <script> in index.html would be blocked.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}
