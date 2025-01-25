import React from 'react';

interface ModeToggleProps {
  mode: 'chat' | 'call';
  toggleMode: () => void;
}

const ModeToggle: React.FC<ModeToggleProps> = ({ mode, toggleMode }) => {
  return (
    <div className="mode-toggle">
      <button id="modeToggle" className="mode-button" onClick={toggleMode}>
        <span id="modeText">{mode === 'chat' ? 'Chat' : 'Call'}</span>
        <span className="mode-icon">&#9881;</span>
      </button>
    </div>
  );
};

export default ModeToggle;