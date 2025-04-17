import React, { useState, useEffect, useRef, useCallback } from 'react';
import './ChatContainer.css';
import './ChatContainerMobile.css';
import Switch from "../components/ui/switch"; // Updated import path
import WavEncoder from 'wav-encoder';
import { FaMicrophone, FaSignOutAlt, FaPaperPlane } from 'react-icons/fa'; // Added Send icon
import { FiMenu } from 'react-icons/fi'; // Added Menu icon for toggle
import { useAuth } from '../contexts/AuthContext';
import { DotLottiePlayer } from '@dotlottie/react-player';
import { motion, AnimatePresence } from 'framer-motion'; // Import motion and AnimatePresence

interface Message {
  role: string;
  content: string;
  timestamp: string;
  event_link?: string;
}

interface ChatContainerProps {
  mode: string;
  toggleMode: () => void;
  chatHistory: Message[];
  isLoading: boolean;
  sendMessage: (message: string) => Promise<void>;
  isAuthLoading?: boolean;
}

declare global {
  interface Window {
    webkitAudioContext: typeof AudioContext
  }
}

const AMPLITUDE_THRESHOLD = 0.01;
const SILENCE_DURATION = 1000;

const ChatContainer: React.FC<ChatContainerProps> = ({ mode, toggleMode, chatHistory, isLoading, sendMessage, isAuthLoading = false }) => {
  const { logout, isAuthenticated } = useAuth();
  const [input, setInput] = useState('');
  const [localChatHistory, setLocalChatHistory] = useState<Message[]>(chatHistory);
  const [isRecording, setIsRecording] = useState(false); // Used in className
  const [isListening, setIsListening] = useState(false); // Used in className and sendAudioToServer
  const [showIntegration, setShowIntegration] = useState(false);
  const messagesEndRef = useRef<null | HTMLDivElement>(null);
  const [hoveredEventLink, setHoveredEventLink] = useState<string | null>(null);
  const [previewPosition, setPreviewPosition] = useState({ top: 0, left: 0 });
  const inputRef = useRef<HTMLInputElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [lastUserMessage, setLastUserMessage] = useState<string | null>(null);
  const [currentAudio, setCurrentAudio] = useState<HTMLAudioElement | null>(null);
  const audioTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [recordingState, setRecordingState] = useState<'idle' | 'recording' | 'playing'>('idle');
  const silenceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const suggestionPrompts = [
    "Hi ATHEN!, what can you do for me",
    "Can you schedule me an event in my calendar for tomorrow Boss meeting from 10 am to 12pm",
    "Athen, remind me off to take my keys when i leave home..."
  ];

  useEffect(() => {
    setLocalChatHistory(chatHistory);
  }, [chatHistory]);

  useEffect(() => {
    const initializeChat = async () => {
      if (isAuthenticated) {
        try {
          const statusResponse = await fetch('/api/auth_status', {
            credentials: 'include',
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json',
            },
          });

          if (!statusResponse.ok) {
            throw new Error('Failed to check authentication status');
          }

          const statusData = await statusResponse.json();
          if (!statusData.authenticated) {
            setLocalChatHistory([]);
          }
        } catch (error) {
          console.error('Error fetching chat history:', error);
          setLocalChatHistory([]);
        }
      } else {
        setLocalChatHistory([]);
      }
    };

    initializeChat();
  }, [isAuthenticated]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const focusInput = useCallback(() => {
    if (inputRef.current) {
      inputRef.current.focus();
    }
  }, []);

  useEffect(() => {
    focusInput();
  }, [focusInput, chatHistory]);

  const playAudioResponse = (audioData: string) => {
    setRecordingState('playing');
    const audio = new Audio(`data:audio/mp3;base64,${audioData}`);
    setCurrentAudio(audio);
    audio.addEventListener('ended', () => {
      setCurrentAudio(null);
      setRecordingState('idle');
    });
    audio.addEventListener('error', (e) => {
      console.error('Error playing audio:', e);
      setCurrentAudio(null);
      setRecordingState('idle');
    });
    audio.play().catch(error => {
      console.error('Error initiating audio playback:', error);
      setCurrentAudio(null);
      setRecordingState('idle');
    });
  };

  const handleChatResponse = async (data: any) => {
    if (data.response) {
      setLocalChatHistory(prev => [...prev, {
        role: 'assistant',
        content: data.response,
        timestamp: new Date().toISOString()
      }]);
    }
    if (data.auth_url) {
      const authWindow = window.open(data.auth_url, 'Google Calendar Authentication', 'width=600,height=600');
      if (authWindow) {
        setLocalChatHistory(prev => [...prev, { role: 'assistant', content: 'Please complete the Google Calendar authentication...', timestamp: new Date().toISOString() }]);
        const checkWindow = setInterval(() => {
          if (authWindow.closed) {
            clearInterval(checkWindow);
            checkAuthStatus(); // Check status after popup closes
          }
        }, 500);
      } else {
        setLocalChatHistory(prev => [...prev, { role: 'assistant', content: 'Please allow popups to authenticate.', timestamp: new Date().toISOString() }]);
      }
    }
    if (data.event_link) {
      setLocalChatHistory(prev => {
        const newHistory = [...prev];
        const lastMessage = newHistory[newHistory.length - 1];
        if (lastMessage && lastMessage.role === 'assistant') {
          lastMessage.event_link = data.event_link;
        }
        return newHistory;
      });
    }
    if (data.audio) {
      playAudioResponse(data.audio);
    }
    scrollToBottom();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !isAuthenticated || isLoading) return; // Prevent sending while loading

    const userMessage = input.trim();
    setInput('');
    setLastUserMessage(userMessage);

    setLocalChatHistory(prev => [...prev, {
        role: 'user',
        content: userMessage,
        timestamp: new Date().toISOString()
    }]);

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ message: userMessage, isInputFromSpeech: false }),
        });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        if (data.error) {
            setLocalChatHistory(prev => [...prev, { role: 'assistant', content: data.response || 'Error processing request.', timestamp: new Date().toISOString() }]);
            return;
        }
        await handleChatResponse(data);
    } catch (error) {
        console.error('Error sending message:', error);
        setLocalChatHistory(prev => [...prev, { role: 'assistant', content: 'Error processing request.', timestamp: new Date().toISOString() }]);
    }
  };

  const checkAuthStatus = useCallback(async () => { // Wrap in useCallback
    try {
        const response = await fetch('/api/auth_status');
        const data = await response.json();
        if (data.authenticated) {
            setLocalChatHistory(prev => [...prev, { role: 'assistant', content: 'Authentication successful! Retrying calendar action...', timestamp: new Date().toISOString() }]);
            if (lastUserMessage) {
                await sendMessage(lastUserMessage);
            }
        } else {
            setLocalChatHistory(prev => [...prev, { role: 'assistant', content: 'Authentication failed or cancelled.', timestamp: new Date().toISOString() }]);
        }
    } catch (error) {
        console.error('Error checking auth status:', error);
        setLocalChatHistory(prev => [...prev, { role: 'assistant', content: 'Error checking authentication status.', timestamp: new Date().toISOString() }]);
    }
  }, [lastUserMessage, sendMessage]); // Add dependencies

  const handleEventLinkHover = (eventLink: string | undefined, event: React.MouseEvent | undefined) => {
    if (eventLink && event) {
      const rect = event.currentTarget.getBoundingClientRect();
      setPreviewPosition({ top: rect.top, left: rect.right + 10 });
      setHoveredEventLink(eventLink);
    } else {
      setHoveredEventLink(null);
    }
  };

  const renderMessage = (message: Message, index: number) => (
    <motion.div
      key={`${message.role}-${message.timestamp}-${index}`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      layout
      className={`message ${message.role}`}
      style={{ userSelect: 'text', WebkitUserSelect: 'text', MozUserSelect: 'text', msUserSelect: 'text' }}
    >
      <span className="message-content" style={{ userSelect: 'text', WebkitUserSelect: 'text', MozUserSelect: 'text', msUserSelect: 'text' }}>{message.content}</span>
      {message.event_link && (
        <a
          href={message.event_link}
          target="_blank"
          rel="noopener noreferrer"
          className="event-link"
          onMouseEnter={(e) => handleEventLinkHover(message.event_link, e)}
          onMouseLeave={() => handleEventLinkHover(undefined, undefined)}
        >
          [Event Link]
        </a>
      )}
    </motion.div>
  );

  const calculateAmplitude = (buffer: Float32Array): number => {
    let sum = 0;
    for (let i = 0; i < buffer.length; i++) { sum += buffer[i] * buffer[i]; }
    return Math.sqrt(sum / buffer.length);
  };

  const startRecording = async () => {
    if (recordingState !== 'idle') return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;
      const processor = audioContext.createScriptProcessor(1024, 1, 1);
      processorRef.current = processor;
      const audioChunks: Float32Array[] = [];
      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);
        const amplitude = calculateAmplitude(inputData);
        audioChunks.push(new Float32Array(inputData));
        if (amplitude > AMPLITUDE_THRESHOLD) {
          if (silenceTimeoutRef.current) { clearTimeout(silenceTimeoutRef.current); silenceTimeoutRef.current = null; }
        } else if (!silenceTimeoutRef.current) {
          silenceTimeoutRef.current = setTimeout(() => { stopRecording(audioContext, processor, audioChunks); }, SILENCE_DURATION);
        }
      };
      source.connect(processor);
      processor.connect(audioContext.destination);
      setRecordingState('recording');
      setIsRecording(true);
    } catch (error) {
      console.error('Error starting recording:', error);
      setRecordingState('idle');
    }
  };

  const stopRecording = (audioContext: AudioContext, processor: ScriptProcessorNode, audioChunks: Float32Array[]) => {
    if (silenceTimeoutRef.current) { 
      clearTimeout(silenceTimeoutRef.current); 
      silenceTimeoutRef.current = null; 
    }
    processor.disconnect();
    
    if (audioContext.state !== 'closed') { 
      audioContext.close().catch(e => console.error("Error closing AudioContext:", e)); 
    }
    if (streamRef.current) { 
      streamRef.current.getTracks().forEach(track => track.stop()); 
      streamRef.current = null; 
    }

    const audioData = audioChunks.reduce((acc, chunk) => {
      const tmp = new Float32Array(acc.length + chunk.length);
      tmp.set(acc, 0);
      tmp.set(chunk, acc.length);
      return tmp;
    }, new Float32Array());

    const sampleRate = audioContext.sampleRate || 44100;
    
    // Create WAV file with proper format for Whisper
    WavEncoder.encode({
      sampleRate: 16000,  // Force 16kHz sample rate
      channelData: [audioData]
    })
    .then((buffer: ArrayBuffer) => {
      const blob = new Blob([buffer], { type: 'audio/wav' });
      sendAudioToServer(blob);
    })
    .catch(e => console.error("Error encoding WAV:", e));
    
    setIsRecording(false);
    if (recordingState === 'recording') { 
      setRecordingState('idle'); 
    }
  };

  const toggleCallMode = async () => {
    if (recordingState === 'idle') { await startRecording(); }
    else if (recordingState === 'recording') {
      if (processorRef.current && audioContextRef.current) {
        stopRecording(audioContextRef.current, processorRef.current, []);
      }
    }
  };

  const sendAudioToServer = async (audioBlob: Blob) => {
    setIsListening(false);
    processorRef.current?.disconnect();
    processorRef.current = null;
    sourceRef.current?.disconnect();
    sourceRef.current = null;
    
    if (audioContextRef.current?.state !== 'closed') {
      audioContextRef.current?.close().catch(e => console.error("Error closing AudioContext:", e));
      audioContextRef.current = null;
    }
    
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }

    const formData = new FormData();
    formData.append('audio', audioBlob, 'audio.wav');  // Ensure .wav extension
    
    try {
      const response = await fetch('/api/speech-to-text', {
        method: 'POST',
        body: formData,
        credentials: 'include'
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      if (data.transcription?.trim()) {
        setLocalChatHistory(prev => [...prev, {
          role: 'user',
          content: data.transcription,
          timestamp: new Date().toISOString()
        }]);
        
        const chatResponse = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            message: data.transcription,
            is_speech: true
          }),
        });
        
        if (!chatResponse.ok) {
          throw new Error(`HTTP error! status: ${chatResponse.status}`);
        }
        
        const chatData = await chatResponse.json();
        setLocalChatHistory(prev => [...prev, {
          role: 'assistant',
          content: chatData.response,
          timestamp: new Date().toISOString()
        }]);
        
        if (chatData.audio) {
          playAudioResponse(chatData.audio);
        } else {
          resetStates();
        }
      } else if (data.error) {
        console.error('Error from server:', data.error);
        setLocalChatHistory(prev => [...prev, {
          role: 'assistant',
          content: `Error: ${data.error}`,
          timestamp: new Date().toISOString()
        }]);
        resetStates();
      } else {
        console.error('No transcription received');
        setLocalChatHistory(prev => [...prev, {
          role: 'assistant',
          content: 'Could not process audio.',
          timestamp: new Date().toISOString()
        }]);
        resetStates();
      }
    } catch (error) {
      console.error('Error sending audio:', error);
      setLocalChatHistory(prev => [...prev, {
        role: 'assistant',
        content: 'Error processing audio.',
        timestamp: new Date().toISOString()
      }]);
      resetStates();
    }
  };

  const resetStates = () => {
    setIsListening(false);
    setIsRecording(false);
    setRecordingState('idle');
    processorRef.current?.disconnect(); processorRef.current = null;
    sourceRef.current?.disconnect(); sourceRef.current = null;
    if (audioContextRef.current?.state !== 'closed') { audioContextRef.current?.close().catch(e => console.error("Error closing AudioContext:", e)); audioContextRef.current = null; }
    streamRef.current?.getTracks().forEach(track => track.stop()); streamRef.current = null;
  };

  const handleIntegrationClick = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
      const response = await fetch('/api/auth/google', { method: 'GET', credentials: 'include' });
      if (!response.ok) throw new Error('Failed to start auth');
      const data = await response.json();
      if (data.authUrl) {
        const width = 500, height = 600;
        const left = window.screenX + (window.outerWidth - width) / 2;
        const top = window.screenY + (window.outerHeight - height) / 2;
        const popup = window.open(data.authUrl, 'Google Sign In', `width=${width},height=${height},left=${left},top=${top},toolbar=0,location=0,menubar=0,status=0`);
        if (popup) {
          const checkPopup = setInterval(async () => {
            if (popup.closed) {
              clearInterval(checkPopup);
              await new Promise(resolve => setTimeout(resolve, 1500));
              checkAuthStatus();
            }
          }, 500);
        } else { throw new Error('Failed to open popup'); }
      }
    } catch (err) {
      const error = err as Error;
      console.error('Error during Google integration:', error);
      setLocalChatHistory(prev => [...prev, { role: 'assistant', content: `Integration error: ${error.message}`, timestamp: new Date().toISOString() }]);
    }
  };

  const handleClearHistory = async () => {
    try {
      const clearResponse = await fetch('/api/clear_chat_history', { method: 'POST', credentials: 'include' });
      if (!clearResponse.ok) throw new Error('Failed to clear history');
      setLocalChatHistory([]);
    } catch (error) {
      console.error('Error clearing chat history:', error);
      setLocalChatHistory(prev => [...prev, { role: 'assistant', content: 'Failed to clear history.', timestamp: new Date().toISOString() }]);
    }
  };

  const handleLogout = async () => {
    try { await logout(); }
    catch (error) { console.error('Error logging out:', error); }
  };

  const renderToggleButton = () => (
    <div className="flex items-center space-x-2">
      <span className={`text-xs font-medium ${mode === 'chat' ? 'text-white' : 'text-gray-300'}`}>
        Chat
      </span>
      <Switch
        checked={mode === 'call'}
        onChange={toggleMode}
      />
      <span className={`text-xs font-medium ${mode === 'call' ? 'text-white' : 'text-gray-300'}`}>
        Call
      </span>
    </div>
  );

  useEffect(() => {
    const audio = currentAudio;
    return () => {
      if (audioTimeoutRef.current) { clearTimeout(audioTimeoutRef.current); audioTimeoutRef.current = null; }
      if (audio) { audio.pause(); audio.currentTime = 0; }
    };
  }, [currentAudio]);

  const renderRecordButton = () => {
    let buttonStyle = ''; let buttonText = '';
    switch (recordingState) {
      case 'recording': buttonStyle = 'bg-red-500 hover:bg-red-600 animate-pulse'; buttonText = 'Recording...'; break;
      case 'playing': buttonStyle = 'bg-purple-500'; buttonText = 'Playing...'; break;
      default: buttonStyle = 'bg-blue-500 hover:bg-blue-600'; buttonText = 'Start Recording';
    }
    return (
      <motion.button
        whileHover={{ scale: recordingState === 'idle' ? 1.05 : 1 }}
        whileTap={{ scale: recordingState === 'idle' ? 0.95 : 1 }}
        onClick={toggleCallMode}
        disabled={recordingState === 'playing'}
        className={`record-button ${buttonStyle} text-white font-medium py-3 px-6 rounded-full flex items-center justify-center gap-2 shadow-md`}
      >
        <FaMicrophone />
        <span>{buttonText}</span>
      </motion.button>
    );
  };

  const LoadingAnimation = () => (
    <div className="loading-animation-container p-4">
      <DotLottiePlayer
        src="/animations/load_anime.json"
        autoplay loop style={{ width: '60px', height: '60px' }}
      />
    </div>
  );

  const handleSuggestionClick = (promptText: string) => {
    setInput(promptText);
    focusInput();
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
      className={`chat-container ${mode === 'call' ? 'call-mode-active' : ''}`}
    >
      <div className="chat-header">
        <span>ATHEN</span>
        <div className="header-controls">
          {renderToggleButton()}
          <motion.button
            whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }}
            className="integration-toggle"
            onClick={() => setShowIntegration(!showIntegration)}
            aria-label="Menu"
          >
             <FiMenu />
          </motion.button>
        </div>
      </div>

      <AnimatePresence>
        {showIntegration && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="integration-container"
          >
            <button onClick={handleIntegrationClick}>Integrate Calendar</button>
            <button onClick={handleClearHistory}>Clear Chat History</button>
            <button onClick={handleLogout} className="logout-button">
              <FaSignOutAlt className="inline-block mr-2" />
              Logout
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {mode === 'chat' ? (
        <>
          <div className="messages" ref={messagesEndRef}>
            {localChatHistory.length === 0 ? (
              <motion.div 
                className="suggestion-prompts-container"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ 
                  duration: 0.5,
                  ease: [0.4, 0, 0.2, 1]
                }}
              >
                <motion.div 
                  className="suggestion-prompts-title"
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2, duration: 0.5 }}
                >
                  Try asking Athen:
                </motion.div>
                {suggestionPrompts.map((prompt, index) => (
                  <motion.button
                    key={index}
                    className="suggestion-prompt-box"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ 
                      delay: 0.3 + index * 0.1, 
                      duration: 0.5,
                      ease: [0.4, 0, 0.2, 1]
                    }}
                    whileHover={{ 
                      scale: 1.02,
                      transition: { duration: 0.2 }
                    }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => handleSuggestionClick(prompt)}
                  >
                    {prompt}
                  </motion.button>
                ))}
              </motion.div>
            ) : (
              <AnimatePresence initial={false}>
                {localChatHistory.map((message, index) => renderMessage(message, index))}
              </AnimatePresence>
            )}
          </div>
          {isLoading && <LoadingAnimation />}
          <motion.form
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.3 }}
            onSubmit={handleSubmit} className="input-area">
            <input
              type="text" id="userInput" ref={inputRef} value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your message..." disabled={isLoading}
              onBlur={focusInput}
            />
            <div className="action-buttons">
              <motion.button
                whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                type="submit" disabled={isLoading || !input.trim()}
                className="send-button"
                aria-label="Send message"
              >
                <FaPaperPlane />
              </motion.button>
            </div>
          </motion.form>
        </>
      ) : (
        <div className="call-container">
          {renderRecordButton()}
        </div>
      )}

      <AnimatePresence>
      {hoveredEventLink && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.9 }}
          className="event-preview"
          style={{ top: `${previewPosition.top}px`, left: `${previewPosition.left}px` }}
        >
          <strong>Google Calendar Event</strong>
          <p>Click link for details.</p>
        </motion.div>
      )}
      </AnimatePresence>

      <AnimatePresence>
      {isAuthLoading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="auth-loading-overlay"
        >
          <LoadingAnimation />
          <p>Authenticating...</p>
        </motion.div>
      )}
      </AnimatePresence>
    </motion.div>
  );
};

export default ChatContainer;
