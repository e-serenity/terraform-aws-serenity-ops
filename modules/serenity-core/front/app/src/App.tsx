import React, { useState } from 'react';
import { DemoProvider, useDemo } from './context/DemoContext';
import { Layout } from './components/layout/Layout';
import { LoginGate } from './components/auth/LoginGate';
import { Overview } from './pages/Overview';
import { Topology } from './pages/Topology';
import { BotModule } from './pages/modules/BotModule';
import { SESModule } from './pages/modules/SESModule';
import { CloudWatchModule } from './pages/modules/CloudWatchModule';
import { FinOpsModule } from './pages/modules/FinOpsModule';
import { TeaserModule } from './pages/modules/TeaserModule';

const AppShell: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<string>('overview');
  const { authStatus, apiNotice, clearApiNotice } = useDemo();

  if (authStatus === 'checking' || authStatus === 'unauthenticated') {
    return <LoginGate />;
  }

  const renderContent = () => {
    switch (currentTab) {
      case 'overview':
        return <Overview setCurrentTab={setCurrentTab} />;
      case 'serenity-bot':
        return <BotModule />;
      case 'topology':
        return <Topology setCurrentTab={setCurrentTab} />;
      case 'serenity-ses':
        return <SESModule setCurrentTab={setCurrentTab} />;
      case 'serenity-cloudwatch':
        return <CloudWatchModule setCurrentTab={setCurrentTab} />;
      case 'serenity-iam':
        return <TeaserModule moduleId="serenity-iam" />;
      case 'serenity-finops':
        return <FinOpsModule />;
      default:
        return <Overview setCurrentTab={setCurrentTab} />;
    }
  };

  return (
    <Layout currentTab={currentTab} setCurrentTab={setCurrentTab}>
      {apiNotice && (
        <div className="mb-4 px-4 py-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs flex items-center justify-between gap-3">
          <span>{apiNotice}</span>
          <button
            onClick={clearApiNotice}
            className="text-amber-300 hover:text-white font-medium shrink-0"
          >
            ✕
          </button>
        </div>
      )}
      {renderContent()}
    </Layout>
  );
};

export const App: React.FC = () => {
  return (
    <DemoProvider>
      <AppShell />
    </DemoProvider>
  );
};

export default App;
