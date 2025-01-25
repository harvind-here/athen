import React, { useState } from 'react';

interface IntegrationToggleProps {
  mode: 'chat' | 'call';
  toggleMode: () => void;
}

const IntegrationToggle: React.FC<IntegrationToggleProps> = ({ mode, toggleMode }) => {
  const [isOpen, setIsOpen] = useState(false);

  const toggleIntegrationContainer = () => {
    setIsOpen(!isOpen);
  };

  const handleGoogleAuth = async () => {
    // Implement Google Calendar authentication logic here
  };

  return (
    <>
      <button className="integration-toggle" onClick={toggleIntegrationContainer}>☰</button>
      {isOpen && (
        <div className="integration-container">
          <button onClick={toggleMode} className="mode-toggle-button">
            Switch to {mode === 'chat' ? 'Call' : 'Chat'} Mode
          </button>
          <button onClick={handleGoogleAuth}>Integrate Calendar</button>
          {/* Add more integration buttons here */}
        </div>
      )}
    </>
  );
};

export default IntegrationToggle;