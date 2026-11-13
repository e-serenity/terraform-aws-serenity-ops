import React, { useState } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useDemo } from '../../context/DemoContext';
import { Sparkles, X, ExternalLink } from 'lucide-react';

interface LayoutProps {
  currentTab: string;
  setCurrentTab: (tab: string) => void;
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ currentTab, setCurrentTab, children }) => {
  const { isLiveMode, t } = useDemo();
  const [bannerDismissed, setBannerDismissed] = useState(false);

  return (
    <div className="flex h-screen bg-slate-950 overflow-hidden font-sans">
      <Sidebar currentTab={currentTab} setCurrentTab={setCurrentTab} />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header currentTab={currentTab} />
        {!isLiveMode && !bannerDismissed && (
          <div className="bg-sky-950/40 border-b border-sky-500/20 px-6 py-2 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-300 shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <Sparkles className="w-3.5 h-3.5 text-sky-400 shrink-0" />
              <span className="truncate">
                <strong className="text-white font-medium">
                  {t('Démo interactive (données AWS simulées)', 'Interactive Demo (simulated AWS data)')}
                </strong>
                {' — '}
                {t(
                  'Testez l’approbation HITL, le chatbot et simulez d’autres modules via « Mode Démo » en haut à droite.',
                  'Try HITL approvals, the chatbot, and toggle modules via “Demo Mode” in the top-right.'
                )}
              </span>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <a
                href="https://registry.terraform.io/modules/e-serenity/serenity-ops/aws/latest"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-violet-300 hover:text-violet-200 font-medium"
              >
                <span>Registry</span>
                <ExternalLink className="w-3 h-3" />
              </a>
              <a
                href="https://github.com/e-serenity/terraform-aws-serenity-ops"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-sky-400 hover:text-sky-300 font-medium"
              >
                <span>GitHub</span>
                <ExternalLink className="w-3 h-3" />
              </a>
              <button
                onClick={() => setBannerDismissed(true)}
                aria-label="Close demo banner"
                className="text-slate-400 hover:text-white p-0.5"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
        <main className="flex-1 overflow-y-auto p-6 bg-slate-950">
          {children}
        </main>
      </div>
    </div>
  );
};
