import React from 'react';
import { Construction } from 'lucide-react';

export const PlaceholderPage: React.FC<{ title: string }> = ({ title }) => (
  <div className="flex flex-col items-center justify-center h-[60vh] text-slate-400">
    <Construction size={64} className="mb-4 opacity-50" />
    <h2 className="text-2xl font-bold text-slate-600 mb-2">{title}</h2>
    <p>This module is currently under construction by the Lab Team.</p>
  </div>
);

