import { createRoot, hydrateRoot } from 'react-dom/client';
import { App } from './App';
import './style.css';
import './pages.css';
import './refinements.css';
const root = document.getElementById('root')!;
if (root.hasChildNodes()) hydrateRoot(root, <App />);
else createRoot(root).render(<App />);
