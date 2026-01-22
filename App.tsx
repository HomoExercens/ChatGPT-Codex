import React, { useState } from 'react';
import { Layout } from './components/Layout';
import { Dashboard } from './views/Dashboard';
import { Training } from './views/Training';
import { Forge } from './views/Forge';
import { Replay } from './views/Replay';
import { NavView } from './types';
import { Construction } from 'lucide-react';
import { Language } from './lib/translations';

const PlaceholderView: React.FC<{ title: string }> = ({ title }) => (
  <div className="flex flex-col items-center justify-center h-[60vh] text-slate-400">
    <Construction size={64} className="mb-4 opacity-50" />
    <h2 className="text-2xl font-bold text-slate-600 mb-2">{title}</h2>
    <p>This module is currently under construction by the Lab Team.</p>
  </div>
);

const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<NavView>(NavView.DASHBOARD);
  const [language, setLanguage] = useState<Language>('ko');

  const toggleLanguage = () => {
    setLanguage(prev => prev === 'ko' ? 'en' : 'ko');
  };

  const renderView = () => {
    switch (currentView) {
      case NavView.DASHBOARD:
        return <Dashboard onNavigate={setCurrentView} lang={language} />;
      case NavView.TRAINING:
        return <Training lang={language} />;
      case NavView.FORGE:
        return <Forge lang={language} />;
      case NavView.REPLAY:
        return <Replay lang={language} />;
      case NavView.RANKED:
        return <PlaceholderView title="Ranked Queue" />;
      case NavView.ANALYTICS:
        return <PlaceholderView title="Deep Analytics" />;
      case NavView.SETTINGS:
        return <PlaceholderView title="Settings" />;
      default:
        return <Dashboard onNavigate={setCurrentView} lang={language} />;
    }
  };

  return (
    <Layout 
      currentView={currentView} 
      onChangeView={setCurrentView}
      lang={language}
      onToggleLang={toggleLanguage}
    >
      {renderView()}
    </Layout>
  );
};

export default App;