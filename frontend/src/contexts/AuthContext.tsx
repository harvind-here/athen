import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

interface User {
  id: string;
  name?: string;
  email?: string;
  isCalendarAuthorized?: boolean;
}

interface AuthContextType {
  user: User | null;
  login: (userId: string, name?: string, email?: string, isCalendarAuthorized?: boolean) => void;
  logout: () => void;
  isLoading: boolean;
  isAuthenticated: boolean;
  handleGoogleSignIn: () => Promise<void>;
  authorizeCalendar: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const isAuthenticated = !!user;

  const checkSession = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetch('/api/auth/session');
      const data = await response.json();
      if (data.user) {
        setUser(data.user);
      } else {
        setUser(null);
      }
    } catch (error) {
      console.error('Error checking session:', error);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, [setIsLoading, setUser]);

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  const login = (userId: string, name?: string, email?: string, isCalendarAuthorized?: boolean) => {
    setUser({ id: userId, name, email, isCalendarAuthorized });
  };

  const logout = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
      setUser(null);
      window.location.href = '/';
    } catch (error) {
      console.error('Error logging out:', error);
    }
  };

  const openAuthWindow = (url: string) => {
    const width = 500, height = 600;
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;
    const authWindow = window.open(url, 'Google Auth', `width=${width},height=${height},left=${left},top=${top}`);

    const handleMessage = (event: MessageEvent) => {
      if (event.source === authWindow && event.data === 'auth-success') {
        checkSession();
        window.removeEventListener('message', handleMessage);
      }
    };

    window.addEventListener('message', handleMessage);
  };

  const handleGoogleSignIn = async () => {
    try {
      const response = await fetch('/api/auth/google/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frontend_origin: window.location.origin }),
      });
      const data = await response.json();
      if (data.authUrl) {
        openAuthWindow(data.authUrl);
      }
    } catch (error) {
      console.error('Error during Google sign in:', error);
    }
  };

  const authorizeCalendar = async () => {
    try {
      const response = await fetch('/api/auth/google/calendar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frontend_origin: window.location.origin }),
      });
      const data = await response.json();
      if (data.authUrl) {
        openAuthWindow(data.authUrl);
      }
    } catch (error) {
      console.error('Error authorizing calendar:', error);
    }
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, isLoading, isAuthenticated, handleGoogleSignIn, authorizeCalendar }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
