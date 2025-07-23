import React, { useState, useEffect } from 'react';
import ChatContainer from './components/ChatContainer';
import LoginPage from './components/LoginPage';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import './App.css';

interface Message {
  role: string;
  content: string;
  timestamp: string;
}

function AppContent() {
  const { user, isLoading } = useAuth();
  const [mode, setMode] = useState('chat');
  const [chatHistory, setChatHistory] = useState<Message[]>([]);
  const [isLoadingChat, setIsLoadingChat] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const toggleMode = () => {
    setMode(mode === 'chat' ? 'call' : 'chat');
  };

  const sendMessage = async (message: string) => {
    if (message.trim() === '' || !user) return;

    setChatHistory(prevHistory => [
      ...prevHistory,
      { role: 'user', content: message, timestamp: new Date().toISOString() }
    ]);

    setIsLoadingChat(true);
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        credentials: 'include',
        headers: { 
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ message, isInputFromSpeech: false }),
      });

      if (!response.ok) {
        if (response.status === 401) {
          window.location.href = '/';
          return;
        }
        throw new Error('Network response was not ok');
      }

      const data = await response.json();

      setChatHistory(prevHistory => [
        ...prevHistory,
        { role: 'assistant', content: data.response, timestamp: new Date().toISOString() }
      ]);
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setIsLoadingChat(false);
    }
  };

  useEffect(() => {
    const fetchChatHistory = async () => {
      if (!user) return;
      
      try {
        const response = await fetch(`/api/conversation_history`, {
          credentials: 'include',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          }
        });
        if (!response.ok) throw new Error('Failed to fetch chat history');
        const data = await response.json();
        setChatHistory(data.conversation_history);
      } catch (error) {
        console.error('Error fetching chat history:', error);
      }
    };

    fetchChatHistory();
  }, [user]);

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const error = urlParams.get('error');

    if (error) {
      setAuthError('Google authentication failed. Please try again.');
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-gray-900"></div>
      </div>
    );
  }

  if (!user) {
    return <LoginPage error={authError} />;
  }

  return (
    <div className="App">
      <ChatContainer 
        mode={mode} 
        toggleMode={toggleMode} 
        chatHistory={chatHistory} 
        isLoading={isLoadingChat} 
        sendMessage={sendMessage} 
      />
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
