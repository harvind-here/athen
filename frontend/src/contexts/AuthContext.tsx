import React, { createContext, useContext, useState, useEffect } from 'react';

interface User {
  id: string;
  isGuest: boolean;
  name?: string;
  email?: string;
}

interface AuthContextType {
  user: User | null;
  login: (userId: string, isGuest: boolean, name?: string) => void;
  logout: () => void;
  isLoading: boolean;
  isAuthenticated: boolean;
  handleGoogleSignIn: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const isAuthenticated = !!user;

  useEffect(() => {
    const checkSession = async () => {
      try {
        const authStatusResponse = await fetch('/api/auth_status', {
          credentials: 'include',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          },
        });
        const authStatusData = await authStatusResponse.json();

        if (authStatusData.authenticated) {
          const sessionResponse = await fetch('/api/auth/session', {
            credentials: 'include',
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json',
            },
          });
          const sessionData = await sessionResponse.json();
          
          if (sessionData.user) {
            setUser(sessionData.user);
          }
        } else {
          setUser(null);
        }
      } catch (error) {
        console.error('Error checking session:', error);
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    checkSession();
  }, [window.location.pathname]); // Re-run checkSession on route change or refresh

  const login = (userId: string, isGuest: boolean, name?: string) => {
    // Set the user state based on data already verified by LoginPage's checkAuthStatus
    const userData = { id: userId, isGuest, name };
    setUser(userData);
    // No need to call POST /api/auth/login here, session should be set by backend OAuth flow
    console.log('AuthContext: User state set after login:', userData);
  };

  const logout = async () => {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
      });
      setUser(null);
      window.location.href = '/'; // Redirect to home after logout
    } catch (error) {
      console.error('Error logging out:', error);
    }
  };

  const handleGoogleSignIn = async () => {
    try {
      const response = await fetch('/api/auth/google', {
        method: 'GET',
        credentials: 'include',
      });
      const data = await response.json();
      
      if (data.auth_url) {
        const width = 500;
        const height = 600;
        const left = window.screenX + (window.outerWidth - width) / 2;
        const top = window.screenY + (window.outerHeight - height) / 2;
        
        const authWindow = window.open(
          data.auth_url,
          'Google Sign In',
          `width=${width},height=${height},left=${left},top=${top}`
        );

        if (authWindow) {
          const checkAuth = setInterval(async () => {
            try {
              if (authWindow.closed) {
                clearInterval(checkAuth);
                const statusResponse = await fetch('/api/auth_status');
                const statusData = await statusResponse.json();
                
                if (statusData.authenticated) {
                  window.location.reload();
                }
              }
            } catch (error) {
              console.error('Error checking auth status:', error);
              clearInterval(checkAuth);
            }
          }, 1000);
        } else {
          console.error('Google sign in window was not opened');
        }
      }
    } catch (error) {
      console.error('Error during Google sign in:', error);
      throw error;
    }
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, isLoading, isAuthenticated, handleGoogleSignIn }}>
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
