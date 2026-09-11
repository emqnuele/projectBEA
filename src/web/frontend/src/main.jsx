import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { AppearanceProvider } from './state/AppearanceProvider';
import { BrainProvider } from './state/BrainProvider';
import { ToastProvider } from './state/ToastProvider';
import { DialogProvider } from './state/DialogProvider';
import { UpdateProvider } from './state/UpdateProvider';
import { GlassFilters } from './components/glass/GlassFilters';
import { DitherField } from './components/atmosphere/DitherField';
import './index.css';

createRoot(document.getElementById('root')).render(
    <StrictMode>
        <AppearanceProvider>
            <ToastProvider>
                <DialogProvider>
                    <BrainProvider>
                        <UpdateProvider>
                            <GlassFilters />
                            <DitherField />
                            <BrowserRouter>
                                <App />
                            </BrowserRouter>
                        </UpdateProvider>
                    </BrainProvider>
                </DialogProvider>
            </ToastProvider>
        </AppearanceProvider>
    </StrictMode>,
);
