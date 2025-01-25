import React from 'react';

interface Message {
  content: string;
  sender: 'user' | 'ai';
}

interface MessageListProps {
  messages: Message[];
}

const MessageList: React.FC<MessageListProps> = ({ messages }) => {
  return (
    <div className="messages">
      {messages.map((message, index) => (
        <div key={index} className={`message ${message.sender}`}>
          <pre>{message.content}</pre>
        </div>
      ))}
    </div>
  );
};

export default MessageList;