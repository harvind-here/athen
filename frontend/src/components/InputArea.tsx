import React, { useState, useRef } from 'react';

interface InputAreaProps {
  sendMessage: (message: string, isVoice: boolean) => void;
}

const InputArea: React.FC<InputAreaProps> = ({ sendMessage }) => {
  const [input, setInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const handleSendMessage = () => {
    if (input.trim()) {
      sendMessage(input, false);
      setInput('');
    }
  };

  const toggleRecording = async () => {
    if (!isRecording) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorderRef.current = new MediaRecorder(stream);
        audioChunksRef.current = [];

        mediaRecorderRef.current.ondataavailable = (event) => {
          audioChunksRef.current.push(event.data);
        };

        mediaRecorderRef.current.onstop = () => {
          const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
          sendAudioToServer(audioBlob);
        };

        mediaRecorderRef.current.start();
        setIsRecording(true);
      } catch (error) {
        console.error('Error starting recording:', error);
      }
    } else {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
    }
  };

  const sendAudioToServer = async (audioBlob: Blob) => {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'audio.webm');

    try {
      const response = await fetch('/api/speech-to-text', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Failed to send audio to server');
      }

      const data = await response.json();
      if (data.transcription) {
        sendMessage(data.transcription, true);
      } else {
        console.error('No transcription available');
      }
    } catch (error) {
      console.error('Error sending audio to server:', error);
    }
  };

  return (
    <div className="input-area">
      <input
        type="text"
        id="userInput"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Type your message..."
        onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
      />
      <div className="action-buttons">
        <button onClick={handleSendMessage}>Send</button>
        <button
          onClick={toggleRecording}
          className={isRecording ? 'recording' : ''}
        >
          {isRecording ? 'Stop Recording' : 'Start Recording'}
        </button>
      </div>
    </div>
  );
};

export default InputArea;