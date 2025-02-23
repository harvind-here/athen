import React, { useState, useEffect, useRef, useCallback } from 'react';
import './ChatContainer.css';
import './ChatContainerMobile.css';
import Switch from "../components/ui/switch"; // Updated import path
import { Label } from "../components/ui/label"; // Updated import path
import WavEncoder from 'wav-encoder';
import { FaMicrophone, FaSignOutAlt } from 'react-icons/fa'; // Add this import for the microphone icon and logout icon
import { useAuth } from '../contexts/AuthContext';
import { DotLottiePlayer } from '@dotlottie/react-player';

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

interface CustomAudioProcessor {
  stop: () => void;
}

declare global {
  interface Window {
    webkitAudioContext: typeof AudioContext
  }
}

const AMPLITUDE_THRESHOLD = 0.01; // Reduced threshold for better sensitivity
const SILENCE_DURATION = 1000; // 1 second of silence before stopping
const RECORDING_TIMEOUT = 2000; // 2 seconds in milliseconds

const ChatContainer: React.FC<ChatContainerProps> = ({ mode, toggleMode, chatHistory, isLoading, sendMessage, isAuthLoading = false }) => {
  const { logout, isAuthenticated, handleGoogleSignIn } = useAuth();
  const [input, setInput] = useState('');
  const [localChatHistory, setLocalChatHistory] = useState<Message[]>(chatHistory);
  const [isRecording, setIsRecording] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [showIntegration, setShowIntegration] = useState(false);
  const messagesEndRef = useRef<null | HTMLDivElement>(null);
  const [audioProcessor, setAudioProcessor] = useState<CustomAudioProcessor | null>(null);
  const [hoveredEventLink, setHoveredEventLink] = useState<string | null>(null);
  const [previewPosition, setPreviewPosition] = useState({ top: 0, left: 0 });
  const inputRef = useRef<HTMLInputElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recordingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [lastUserMessage, setLastUserMessage] = useState<string | null>(null);
  const [currentAudio, setCurrentAudio] = useState<HTMLAudioElement | null>(null);
  const [canRecord, setCanRecord] = useState(true);
  const audioTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isWaitingForResponse, setIsWaitingForResponse] = useState(false);
  const [recordingState, setRecordingState] = useState<'idle' | 'recording' | 'playing'>('idle');
  const silenceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setLocalChatHistory(chatHistory);
  }, [chatHistory]);

  useEffect(() => {
    const initializeChat = async () => {
      if (isAuthenticated) {
        try {
          const response = await fetch('/api/conversation_history', {
            method: 'GET',
            credentials: 'include',
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json'
            }
          });

          if (!response.ok) {
            if (response.status === 401) {
              // Handle authentication error
              window.location.href = '/';
              return;
            }
            throw new Error('Failed to fetch chat history');
          }

          const data = await response.json();
          if (data.conversation_history) {
            setLocalChatHistory(data.conversation_history);
          } else {
            setLocalChatHistory([]); // Reset if no history
          }
        } catch (error) {
          console.error('Error fetching chat history:', error);
          setLocalChatHistory([]); // Reset on error
        }
      } else {
        setLocalChatHistory([]); // Reset when not authenticated
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
  }, [focusInput, chatHistory]); // Re-focus after messages update

  const handleChatResponse = async (data: any) => {
    // First handle the response text
    if (data.response) {
      setLocalChatHistory(prev => [...prev, {
        role: 'assistant',
        content: data.response,
        timestamp: new Date().toISOString()
      }]);
    }

    // Handle auth URL if present
    if (data.auth_url) {
      const authWindow = window.open(
        data.auth_url,
        'Google Calendar Authentication',
        'width=600,height=600'
      );

      if (authWindow) {
        // Add a message about authentication
        setLocalChatHistory(prev => [...prev, {
          role: 'assistant',
          content: 'Please complete the Google Calendar authentication in the popup window...',
          timestamp: new Date().toISOString()
        }]);

        // Poll for authentication status
        const checkWindow = setInterval(() => {
          if (authWindow.closed) {
            clearInterval(checkWindow);
            // Check authentication status
            fetch('/api/auth_status')
              .then(response => response.json())
              .then(data => {
                if (data.authenticated) {
                  // Show success message and retry last operation
                  setLocalChatHistory(prev => [...prev, {
                    role: 'assistant',
                    content: 'Authentication successful! I\'ll now try to create the calendar event.',
                    timestamp: new Date().toISOString()
                  }]);
                  
                  // Retry the last operation if needed
                  if (lastUserMessage) {
                    sendMessage(lastUserMessage);
                  }
                } else {
                  setLocalChatHistory(prev => [...prev, {
                    role: 'assistant',
                    content: 'Authentication was cancelled or failed. Please try again when you want to use calendar features.',
                    timestamp: new Date().toISOString()
                  }]);
                }
              })
              .catch(error => {
                console.error('Error checking auth status:', error);
                setLocalChatHistory(prev => [...prev, {
                  role: 'assistant',
                  content: 'There was an error checking the authentication status. Please try again.',
                  timestamp: new Date().toISOString()
                }]);
              });
          }
        }, 500);
      } else {
        setLocalChatHistory(prev => [...prev, {
          role: 'assistant',
          content: 'Please allow popups to authenticate with Google Calendar.',
          timestamp: new Date().toISOString()
        }]);
      }
    }

    // Handle event link if present
    if (data.event_link) {
      // Update the last assistant message to include the event link
      setLocalChatHistory(prev => {
        const newHistory = [...prev];
        const lastMessage = newHistory[newHistory.length - 1];
        if (lastMessage && lastMessage.role === 'assistant') {
          lastMessage.event_link = data.event_link;
        }
        return newHistory;
      });
    }

    // Handle audio if present
    if (data.audio) {
      playAudioResponse(data.audio);
    }

    // Scroll to bottom after updating chat
    scrollToBottom();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !isAuthenticated) return;

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
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({
                message: userMessage,
                isInputFromSpeech: false
            }),
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        if (data.error) {
            setLocalChatHistory(prev => [...prev, {
                role: 'assistant',
                content: data.response || 'Sorry, there was an error processing your request.',
                timestamp: new Date().toISOString()
            }]);
            return;
        }

        await handleChatResponse(data);

    } catch (error) {
        console.error('Error sending message:', error);
        setLocalChatHistory(prev => [...prev, {
            role: 'assistant',
            content: 'Sorry, there was an error processing your request.',
            timestamp: new Date().toISOString()
        }]);
    }
  };

  const handleAuthUrl = (authUrl: string) => {
    const authWindow = window.open(
        authUrl,
        'Google Calendar Authentication',
        'width=600,height=600'
    );

    if (authWindow) {
        setLocalChatHistory(prev => [...prev, {
            role: 'assistant',
            content: 'Please complete the Google Calendar authentication in the popup window...',
            timestamp: new Date().toISOString()
        }]);

        const checkWindow = setInterval(() => {
            if (authWindow.closed) {
                clearInterval(checkWindow);
                checkAuthStatus();
            }
        }, 500);
    } else {
        setLocalChatHistory(prev => [...prev, {
            role: 'assistant',
            content: 'Please allow popups to authenticate with Google Calendar.',
            timestamp: new Date().toISOString()
        }]);
    }
  };

  const checkAuthStatus = async () => {
    try {
        const response = await fetch('/api/auth_status');
        const data = await response.json();
        
        if (data.authenticated) {
            setLocalChatHistory(prev => [...prev, {
                role: 'assistant',
                content: 'Authentication successful! I\'ll now try to create the calendar event.',
                timestamp: new Date().toISOString()
            }]);
            
            // Retry the last operation
            if (lastUserMessage) {
                await sendMessage(lastUserMessage);
            }
        } else {
            setLocalChatHistory(prev => [...prev, {
                role: 'assistant',
                content: 'Authentication was cancelled or failed. Please try again when you want to use calendar features.',
                timestamp: new Date().toISOString()
            }]);
        }
    } catch (error) {
        console.error('Error checking auth status:', error);
        setLocalChatHistory(prev => [...prev, {
            role: 'assistant',
            content: 'There was an error checking the authentication status. Please try again.',
            timestamp: new Date().toISOString()
        }]);
    }
  };

  const playAudioResponse = (audioData: string) => {
    setRecordingState('playing');
    
    const audio = new Audio(`data:audio/mp3;base64,${audioData}`);
    setCurrentAudio(audio);

    audio.addEventListener('ended', () => {
      setCurrentAudio(null);
      setRecordingState('idle');
    });

    audio.addEventListener('error', () => {
      console.error('Error playing audio');
      setCurrentAudio(null);
      setRecordingState('idle');
    });

    audio.play().catch(error => {
      console.error('Error playing audio:', error);
      setRecordingState('idle');
    });
  };

  const handleEventLinkHover = (eventLink: string | undefined, event: React.MouseEvent | undefined) => {
    if (eventLink && event) {
      const rect = event.currentTarget.getBoundingClientRect();
      setPreviewPosition({
        top: rect.top,
        left: rect.right + 10, // 10px to the right of the message
      });
      setHoveredEventLink(eventLink);
    } else {
      setHoveredEventLink(null);
    }
  };

  const renderMessage = (message: Message, index: number) => (
    <div key={index} className={`message ${message.role}`} style={{ userSelect: 'text', WebkitUserSelect: 'text', MozUserSelect: 'text', msUserSelect: 'text' }}>
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
    </div>
  );

  const startListening = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      audioContextRef.current = new AudioContext();
      sourceRef.current = audioContextRef.current.createMediaStreamSource(stream);
      processorRef.current = audioContextRef.current.createScriptProcessor(1024, 1, 1);

      processorRef.current.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);
        const amplitude = calculateAmplitude(inputData);

        if (amplitude > AMPLITUDE_THRESHOLD && !isRecording) {
          startRecording();
        }
      };

      sourceRef.current.connect(processorRef.current);
      processorRef.current.connect(audioContextRef.current.destination);
      setIsListening(true);
    } catch (error) {
      console.error('Error starting audio monitoring:', error);
    }
  };

  const stopListening = () => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    setIsListening(false);
  };

  const calculateAmplitude = (buffer: Float32Array): number => {
    let sum = 0;
    for (let i = 0; i < buffer.length; i++) {
      sum += buffer[i] * buffer[i];
    }
    return Math.sqrt(sum / buffer.length);
  };

  const startRecording = async () => {
    if (recordingState !== 'idle') return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const audioContext = new AudioContext();
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

        // Reset silence timeout if sound is detected
        if (amplitude > AMPLITUDE_THRESHOLD) {
          if (silenceTimeoutRef.current) {
            clearTimeout(silenceTimeoutRef.current);
            silenceTimeoutRef.current = null;
          }
        } else if (!silenceTimeoutRef.current) {
          // Start silence timeout when amplitude drops below threshold
          silenceTimeoutRef.current = setTimeout(() => {
            stopRecording(audioContext, processor, audioChunks);
          }, SILENCE_DURATION);
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

  const stopRecording = (
    audioContext: AudioContext,
    processor: ScriptProcessorNode,
    audioChunks: Float32Array[]
  ) => {
    if (silenceTimeoutRef.current) {
      clearTimeout(silenceTimeoutRef.current);
      silenceTimeoutRef.current = null;
    }

    processor.disconnect();
    audioContext.close();

    // Clean up audio resources
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

    WavEncoder.encode({
      sampleRate: audioContext.sampleRate,
      channelData: [audioData]
    }).then((buffer: ArrayBuffer) => {
      const blob = new Blob([buffer], { type: 'audio/wav' });
      sendAudioToServer(blob);
    });

    setIsRecording(false);
  };

  const toggleCallMode = async () => {
    if (recordingState === 'idle') {
      await startRecording();
    } else if (recordingState === 'recording') {
      // Force stop recording if user clicks button
      if (processorRef.current && audioContextRef.current) {
        const audioChunks: Float32Array[] = []; // Added type annotation
        stopRecording(audioContextRef.current, processorRef.current, audioChunks);
      }
    }
    // Do nothing if state is 'playing'
  };

  const sendAudioToServer = async (audioBlob: Blob) => {
    // Set states to prevent new recordings
    setIsWaitingForResponse(true);
    setCanRecord(false);
    setIsListening(false);
    
    // Ensure all audio processes are stopped
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }

    const formData = new FormData();
    formData.append('audio', audioBlob, 'audio.wav');

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
      console.log("Speech-to-text response:", data);

      if (data.transcription && data.transcription.trim() !== "") {
        setLocalChatHistory(prevHistory => [...prevHistory, { role: 'user', content: data.transcription, timestamp: new Date().toISOString() }]);
        
        // Send transcribed text to chat API with is_speech flag
        const chatResponse = await fetch('/api/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
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
        
        setLocalChatHistory(prevHistory => [...prevHistory, {
          role: 'assistant',
          content: chatData.response,
          timestamp: new Date().toISOString()
        }]);

        // Play audio response if available
        if (chatData.audio) {
          playAudioResponse(chatData.audio);
        } else {
          // If no audio response, reset states
          setIsWaitingForResponse(false);
          setCanRecord(true);
        }

      } else if (data.error) {
        console.error('Error from server:', data.error);
        setLocalChatHistory(prevHistory => [...prevHistory, { role: 'assistant', content: `Sorry, an error occurred: ${data.error}`, timestamp: new Date().toISOString() }]);
        resetStates();
      } else {
        console.error('No transcription or error received from server');
        setLocalChatHistory(prevHistory => [...prevHistory, { role: 'assistant', content: 'Sorry, I couldn\'t process the audio. Please try again.', timestamp: new Date().toISOString() }]);
        resetStates();
      }
    } catch (error) {
      console.error('Error sending audio to server:', error);
      setLocalChatHistory(prevHistory => [...prevHistory, { role: 'assistant', content: 'An error occurred while processing the audio. Please try again.', timestamp: new Date().toISOString() }]);
      resetStates();
    }
  };

  // Add new helper function to reset states
  const resetStates = () => {
    setIsWaitingForResponse(false);
    setCanRecord(true);
    setIsListening(false);
    setIsRecording(false);
    
    // Clean up audio resources
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
  };

  const handleIntegrationClick = async () => {
    try {
      // First clear any existing auth state
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        }
      });

      const response = await fetch('/api/auth/google', {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error('Failed to start authentication process');
      }

      const data = await response.json();
      if (data.authUrl) {
        const width = 500;
        const height = 600;
        const left = window.screenX + (window.outerWidth - width) / 2;
        const top = window.screenY + (window.outerHeight - height) / 2;

        // Open popup with same-origin and include credentials
        const popup = window.open(
          data.authUrl,
          'Google Sign In',
          `width=${width},height=${height},left=${left},top=${top},toolbar=0,location=0,menubar=0,status=0`
        );

        if (popup) {
          const checkPopup = setInterval(async () => {
            if (popup.closed) {
              clearInterval(checkPopup);
              // Wait a bit for the server to process the auth
              await new Promise(resolve => setTimeout(resolve, 2000));

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
                if (statusData.authenticated) {
                  // Update local auth state
                  if (handleGoogleSignIn) {
                    await handleGoogleSignIn();
                  }
                  // Reload the page to ensure fresh state
                  window.location.reload();
                } else {
                  console.error('Authentication failed');
                  setLocalChatHistory(prev => [...prev, {
                    role: 'assistant',
                    content: 'Authentication failed. Please try again.',
                    timestamp: new Date().toISOString()
                  }]);
                }
              } catch (error) {
                console.error('Error checking authentication status:', error);
                setLocalChatHistory(prev => [...prev, {
                  role: 'assistant',
                  content: 'Error checking authentication status. Please try again.',
                  timestamp: new Date().toISOString()
                }]);
              }
            }
          }, 500);
        } else {
          throw new Error('Failed to open authentication popup');
        }
      }
    } catch (err) {
      const error = err as Error;
      console.error('Error during Google integration:', error);
      setLocalChatHistory(prev => [...prev, {
        role: 'assistant',
        content: `Error during Google integration: ${error.message}. Please try again.`,
        timestamp: new Date().toISOString()
      }]);
    }
  };

  const handleClearHistory = async () => {
    try {
      // Clear data in the database
      const clearResponse = await fetch('/api/clear_chat_history', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      });

      if (!clearResponse.ok) {
        throw new Error('Failed to clear conversation history');
      }

      // Clear local state only after successful server clear
      setLocalChatHistory([]);
    } catch (error) {
      console.error('Error clearing chat history:', error);
      setLocalChatHistory(prev => [...prev, {
        role: 'assistant',
        content: 'Failed to clear chat history. Please try again.',
        timestamp: new Date().toISOString()
      }]);
    }
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error('Error logging out:', error);
    }
  };

  const renderLoadingAnimation = () => (
    <div className="loading-animation">
      <div className="dot"></div>
      <div className="dot"></div>
      <div className="dot"></div>
    </div>
  );

  // Update the renderToggleButton function
  const renderToggleButton = () => (
    <div className="flex items-center space-x-3">
      <span className={`text-sm ${mode === 'chat' ? 'text-blue-600 font-small' : 'text-gray-500'}`}>
        Chat
      </span>
      <Switch
        checked={mode === 'call'}
        onChange={toggleMode}
      />
      <span className={`text-sm ${mode === 'call' ? 'text-blue-600 font-small' : 'text-gray-500'}`}>
        Call
      </span>
    </div>
  );

  // Add cleanup function for audio timeouts
  const cleanupAudioTimeouts = () => {
    if (audioTimeoutRef.current) {
      clearTimeout(audioTimeoutRef.current);
      audioTimeoutRef.current = null;
    }
  };

  // Add cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupAudioTimeouts();
      if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
      }
    };
  }, []);

  // Modify the button render to show recording state
  const renderRecordButton = () => {
    let buttonStyle = '';
    let buttonText = '';

    switch (recordingState) {
      case 'recording':
        buttonStyle = 'bg-green-500 hover:bg-green-600';
        buttonText = 'Recording...';
        break;
      case 'playing':
        buttonStyle = 'bg-red-500 hover:bg-red-600';
        buttonText = 'Playing Response...';
        break;
      default:
        buttonStyle = 'bg-blue-500 hover:bg-blue-600';
        buttonText = 'Start Recording';
    }

    return (
      <button 
        onClick={toggleCallMode}
        disabled={recordingState === 'playing'}
        className={`record-button ${buttonStyle} text-white font-bold py-2 px-4 rounded-full flex items-center justify-center gap-2`}
      >
        <FaMicrophone />
        <span>{buttonText}</span>
      </button>
    );
  };

  // Add loading animation component
  const LoadingAnimation = () => (
    <div className="loading-animation-container">
      <DotLottiePlayer
        src="https://lottie.host/5ee578b1-8ceb-4f9f-a838-5b32482d2688/gyXXBC7ERf.lottie"
        autoplay
        loop
        style={{ width: '100px', height: '100px' }}
      />
    </div>
  );

  return (
    <div className={`chat-container ${mode === 'call' ? 'dark-theme' : ''} ${isRecording || isListening ? 'highlight-border' : ''}`}>
      <div className="chat-header">
        <span>ATHEN</span>
        <div className="header-controls">
          {renderToggleButton()}
          <button className="integration-toggle" onClick={() => setShowIntegration(!showIntegration)}>☰</button>
        </div>
      </div>
      <div className="integration-container" style={{ display: showIntegration ? 'block' : 'none' }}>
        <button onClick={handleIntegrationClick}>Integrate Calendar</button>
        <button onClick={handleClearHistory}>Clear Chat History</button>
        <button onClick={handleLogout} className="text-red-600 hover:text-red-700">
          <FaSignOutAlt className="inline-block mr-2" />
          Logout
        </button>
      </div>
      {mode === 'chat' ? (
        <>
          <div className="messages" ref={messagesEndRef}>
            {localChatHistory.map((message, index) => renderMessage(message, index))}
          </div>
          {isLoading && (
            <div className="chat-loading-container">
              <LoadingAnimation />
            </div>
          )}
          <form onSubmit={handleSubmit} className="input-area">
            <input
              type="text"
              id="userInput"
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your message..."
              disabled={isLoading}
              onBlur={focusInput}
            />
            <div className="action-buttons">
              <button type="submit" disabled={isLoading}>Send</button>
            </div>
          </form>
        </>
      ) : (
        <div className="call-container">
          {renderRecordButton()}
        </div>
      )}
      {hoveredEventLink && (
        <div 
          className="event-preview"
          style={{
            top: `${previewPosition.top}px`,
            left: `${previewPosition.left}px`,
          }}
        >
          <h3>Event Preview</h3>
          <p>This is a Google Calendar event.</p>
          <p>Click the [Event Link] to view full details.</p>
        </div>
      )}
      {isAuthLoading && (
        <div className="auth-loading-overlay">
          <LoadingAnimation />
          <p>Authenticating...</p>
        </div>
      )}
    </div>
  );
};

export default ChatContainer;