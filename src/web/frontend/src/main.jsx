import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { AppearanceProvider } from './state/AppearanceProvider';
import { BrainProvider } from './state/BrainProvider';
import { ToastProvider } from './state/ToastProvider';
import { DialogProvider } from './state/DialogProvider';
import { GlassFilters } from './components/glass/GlassFilters';
import { DitherField } from './components/atmosphere/DitherField';
import './index.css';

createRoot(document.getElementById('root')).render(
    <StrictMode>
        <AppearanceProvider>
            <ToastProvider>
                <DialogProvider>
                    <BrainProvider>
                        <GlassFilters />
                        <DitherField />
                        <BrowserRouter>
                            <App />
                        </BrowserRouter>
                    </BrainProvider>
                </DialogProvider>
            </ToastProvider>
        </AppearanceProvider>
    </StrictMode>,
);
