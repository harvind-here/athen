import React, { useState, useEffect, useRef, useCallback } from 'react';
import './ChatContainer.css';
import { Switch } from "../components/ui/switch"; // Updated import path
import { Label } from "../components/ui/label"; // Updated import path
import WavEncoder from 'wav-encoder';
import { FaMicrophone } from 'react-icons/fa'; // Add this import for the microphone icon

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
}

interface CustomAudioProcessor {
  stop: () => void;
}

const ChatContainer: React.FC<ChatContainerProps> = ({ mode, toggleMode, chatHistory, isLoading, sendMessage }) => {
  const [input, setInput] = useState('');
  const [localChatHistory, setLocalChatHistory] = useState<Message[]>(chatHistory);
  const [isRecording, setIsRecording] = useState(false);
  const [showIntegration, setShowIntegration] = useState(false);
  const messagesEndRef = useRef<null | HTMLDivElement>(null);
  const [audioProcessor, setAudioProcessor] = useState<CustomAudioProcessor | null>(null);
  const [hoveredEventLink, setHoveredEventLink] = useState<string | null>(null);
  const [previewPosition, setPreviewPosition] = useState({ top: 0, left: 0 });
  const inputRef = useRef<HTMLInputElement>(null);
  const [showClearConfirmation, setShowClearConfirmation] = useState(false);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const [isAnimating, setIsAnimating] = useState(false);
  const [lastUserMessage, setLastUserMessage] = useState<string | null>(null);

  useEffect(() => {
    setLocalChatHistory(chatHistory);
  }, [chatHistory]);

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
    if (!input.trim()) return;

    const userMessage = input.trim();
    setInput('');
    setLastUserMessage(userMessage);

    // Immediately add user message to chat
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
            body: JSON.stringify({
                message: userMessage,
                isInputFromSpeech: false
            }),
        });

        const data = await response.json();
        
        if (data.error) {
            // Handle error response
            setLocalChatHistory(prev => [...prev, {
                role: 'assistant',
                content: data.response || 'Sorry, there was an error processing your request.',
                timestamp: new Date().toISOString()
            }]);
            return;
        }

        // Add assistant's response to chat
        setLocalChatHistory(prev => [...prev, {
            role: 'assistant',
            content: data.response,
            timestamp: new Date().toISOString(),
            event_link: data.event_link
        }]);

        // Handle authentication if needed
        if (data.auth_url) {
            handleAuthUrl(data.auth_url);
        }

        // Handle audio if present
        if (data.audio) {
            playAudioResponse(data.audio);
        }

        // Scroll to bottom
        scrollToBottom();

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
    const audio = new Audio(`data:audio/mp3;base64,${audioData}`);
    setIsAudioPlaying(true);
    setIsAnimating(true);
    audio.play().catch(error => console.error('Error playing audio:', error));
    audio.onended = () => {
      setIsAudioPlaying(false);
      setIsAnimating(false);
    };
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
    <div key={index} className={`message ${message.role}`}>
      <span className="message-content">{message.content}</span>
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

  const toggleRecording = async () => {
    if (!isRecording) {
      setIsAnimating(true);
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const audioContext = new AudioContext();
        const source = audioContext.createMediaStreamSource(stream);
        const processor = audioContext.createScriptProcessor(1024, 1, 1);
        
        const audioChunks: Float32Array[] = [];

        processor.onaudioprocess = (e) => {
          const inputData = e.inputBuffer.getChannelData(0);
          audioChunks.push(new Float32Array(inputData));
        };

        source.connect(processor);
        processor.connect(audioContext.destination);

        setAudioProcessor({
          stop: () => {
            source.disconnect();
            processor.disconnect();
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
          }
        });

        setIsRecording(true);
      } catch (error) {
        console.error('Error starting recording:', error);
      }
    } else {
      audioProcessor?.stop();
      setAudioProcessor(null);
      setIsRecording(false);
      setIsAnimating(false);
    }
  };

  const sendAudioToServer = async (audioBlob: Blob) => {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'audio.wav');

    try {
      const response = await fetch('/api/speech-to-text', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log("Speech-to-text response:", data);

      if (data.transcription && data.transcription.trim() !== "") {
        // Add the transcribed text as a user message
        setLocalChatHistory(prevHistory => [...prevHistory, { role: 'user', content: data.transcription, timestamp: new Date().toISOString() }]);
        // Then send the transcribed text to the chat function
        await sendMessage(data.transcription);
      } else if (data.error) {
        console.error('Error from server:', data.error);
        setLocalChatHistory(prevHistory => [...prevHistory, { role: 'assistant', content: `Sorry, an error occurred: ${data.error}`, timestamp: new Date().toISOString() }]);
      } else {
        console.error('No transcription or error received from server');
        setLocalChatHistory(prevHistory => [...prevHistory, { role: 'assistant', content: 'Sorry, I couldn\'t process the audio. Please try again.', timestamp: new Date().toISOString() }]);
      }
    } catch (error) {
      console.error('Error sending audio to server:', error);
      setLocalChatHistory(prevHistory => [...prevHistory, { role: 'assistant', content: 'An error occurred while processing the audio. Please try again.', timestamp: new Date().toISOString() }]);
    }
  };

  const handleGoogleAuth = async () => {
    try {
      const response = await fetch('/api/auth_callback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: "Authenticate with Google Calendar" }),
      });
      const data = await response.json();
      if (data.auth_url) {
        console.log("Received auth URL:", data.auth_url);
        // Open the auth URL in a new window
        const authWindow = window.open(data.auth_url, '_blank', 'width=600,height=600');
        if (authWindow) {
          // Poll for authentication status
          const pollTimer = setInterval(async () => {
            try {
              const statusResponse = await fetch('/api/auth_status');
              const statusData = await statusResponse.json();
              if (statusData.authenticated) {
                clearInterval(pollTimer);
                authWindow.close();
                alert("Authentication successful!");
                // Refresh the page or update the UI to reflect the new authentication state
                window.location.reload();
              }
            } catch (error) {
              console.error("Error checking auth status:", error);
            }
          }, 2000);
        } else {
          console.error("Failed to open auth window. It may have been blocked by a popup blocker.");
          alert("Please allow popups for this site to authenticate with Google Calendar.");
        }
      } else {
        console.error('No auth_url received from the server');
        alert("Failed to start authentication process. Please try again.");
      }
    } catch (error) {
      console.error('Error:', error);
      alert("An error occurred during authentication. Please try again.");
    }
  };

  const handleClearHistory = async () => {
    setShowClearConfirmation(true);
  };

  const confirmClearHistory = async () => {
    try {
      const response = await fetch('/api/clear_chat_history', {
        method: 'POST',
      });

      if (response.ok) {
        setLocalChatHistory([]);
        setShowClearConfirmation(false);
      } else {
        console.error('Failed to clear chat history');
      }
    } catch (error) {
      console.error('Error clearing chat history:', error);
    }
  };

  const renderLoadingAnimation = () => (
    <div className="loading-animation">
      <div className="dot"></div>
      <div className="dot"></div>
      <div className="dot"></div>
    </div>
  );

  const renderToggleButton = () => (
    <button 
      className={`mode-toggle-button ${mode === 'call' ? 'active' : ''}`} 
      onClick={toggleMode}
    >
      <span className="mode-label">{mode === 'chat' ? 'Chat' : 'Call'}</span>
    </button>
  );

  return (
    <div className={`chat-container ${mode === 'call' ? 'dark-theme' : ''} ${isRecording || isAudioPlaying ? 'highlight-border' : ''}`}>
      <div className="chat-header">
        <span>ATHEN</span>
        <div className="header-controls">
          {renderToggleButton()}
          <button className="integration-toggle" onClick={() => setShowIntegration(!showIntegration)}>☰</button>
        </div>
      </div>
      <div className="integration-container" style={{ display: showIntegration ? 'block' : 'none' }}>
        <button onClick={handleGoogleAuth}>Integrate Calendar</button>
        <button onClick={handleClearHistory}>Clear Chat History</button>
      </div>
      {mode === 'chat' ? (
        <>
          <div className="messages" ref={messagesEndRef}>
            {localChatHistory.map((message, index) => renderMessage(message, index))}
          </div>
          {isLoading && (
            <div className="loading-container">
              {renderLoadingAnimation()}
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
          <button 
            id="recordButton"
            onClick={toggleRecording}
            className={`record-button ${isRecording ? 'recording' : ''} ${isAnimating ? 'animating' : ''}`}
          >
            <FaMicrophone />
            <span>Speak with Athen</span>
          </button>
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
      {showClearConfirmation && (
        <div className="clear-confirmation-overlay">
          <div className="clear-confirmation-dialog">
            <p>Are you sure you want to clear the chat history?</p>
            <p>This action cannot be undone.</p>
            <div className="clear-confirmation-buttons">
              <button onClick={() => setShowClearConfirmation(false)}>Cancel</button>
              <button onClick={confirmClearHistory}>OK</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ChatContainer;