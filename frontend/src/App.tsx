import React, { useState, useEffect } from 'react';
import ChatContainer from './components/ChatContainer';
import './App.css';

interface Message {
  role: string;
  content: string;
  timestamp: string;
}

function App() {
  const [mode, setMode] = useState('chat');
  const [chatHistory, setChatHistory] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const toggleMode = () => {
    setMode(mode === 'chat' ? 'call' : 'chat');
  };

  const sendMessage = async (message: string) => {
    if (message.trim() === '') return;

    // Update chat history immediately with the user's message
    setChatHistory(prevHistory => [
      ...prevHistory,
      { role: 'user', content: message, timestamp: new Date().toISOString() }
    ]);

    setIsLoading(true);
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, isInputFromSpeech: false }),
      });

      if (!response.ok) throw new Error('Network response was not ok');

      const data = await response.json();

      // Update chat history with the assistant's response
      setChatHistory(prevHistory => [
        ...prevHistory,
        { role: 'assistant', content: data.response, timestamp: new Date().toISOString() }
      ]);

      // ... rest of the function (handling audio, etc.)
    } catch (error) {
      console.error('Error:', error);
      // Optionally, update chat history with an error message
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    // Fetch initial chat history from the server
    const fetchChatHistory = async () => {
      try {
        const response = await fetch('/api/conversation_history');
        if (!response.ok) throw new Error('Failed to fetch chat history');
        const data = await response.json();
        setChatHistory(data.conversation_history);
      } catch (error) {
        console.error('Error fetching chat history:', error);
      }
    };

    fetchChatHistory();
  }, []);

  return (
    <div className="App">
      <ChatContainer 
        mode={mode} 
        toggleMode={toggleMode} 
        chatHistory={chatHistory} 
        isLoading={isLoading} 
        sendMessage={sendMessage} 
      />
    </div>
  );
}

export default App;