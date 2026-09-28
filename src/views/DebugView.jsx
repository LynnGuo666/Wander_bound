import React from 'react';
import { ArrowLeft } from 'lucide-react';
import InferenceView from './InferenceView.jsx';
import DeveloperSettingsView from './DeveloperSettingsView.jsx';

export default function DebugView({ onSaved, onBack }) {
  return <div className="debug-page page-enter">
    <button type="button" className="text-button" onClick={onBack}><ArrowLeft size={16} />返回设置</button>
    <InferenceView />
    <section className="debug-providers"><DeveloperSettingsView onSaved={onSaved} /></section>
  </div>;
}
