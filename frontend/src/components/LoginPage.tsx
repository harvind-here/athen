import React, { useState, useEffect } from 'react';
import { FcGoogle } from 'react-icons/fc';
import { FaUser } from 'react-icons/fa';

interface LoginPageProps {
  onLogin: (userId: string, isGuest: boolean, name?: string) => void;
  error?: string | null;
}

const LoginPage: React.FC<LoginPageProps> = ({ onLogin, error }) => {
  const [guestName, setGuestName] = useState('');
  const [showGuestForm, setShowGuestForm] = useState(false);
  const [authWindow, setAuthWindow] = useState<Window | null>(null);

  // Check auth status on mount and when auth window closes
  const checkAuthStatus = async () => {
    try {
      const authStatusResponse = await fetch('/api/auth_status', {
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
      });
      const authStatusData = await authStatusResponse.json();

      if (authStatusData.authenticated && authStatusData.user) {
        onLogin(authStatusData.user.id, authStatusData.user.isGuest, authStatusData.user.name);
        return true;
      }
      return false;
    } catch (error) {
      console.error('Error checking auth status:', error);
      return false;
    }
  };

  // Check auth status on mount
  useEffect(() => {
    checkAuthStatus();
  }, []);

  // Monitor popup window
  useEffect(() => {
    if (!authWindow) return;

    const checkPopup = setInterval(async () => {
      if (authWindow.closed) {
        clearInterval(checkPopup);
        setAuthWindow(null);
        
        // Wait a bit for the session to be properly set
        setTimeout(async () => {
          await checkAuthStatus();
        }, 1000);
      }
    }, 500);

    return () => clearInterval(checkPopup);
  }, [authWindow]);

  const handleGoogleLogin = async () => {
    try {
      const isAuthenticated = await checkAuthStatus();
      if (!isAuthenticated) {
        const response = await fetch('/api/auth/google', {
          credentials: 'include',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          },
        });
        const data = await response.json();
        if (data.authUrl) {
          const width = 500;
          const height = 600;
          const left = window.screenX + (window.outerWidth - width) / 2;
          const top = window.screenY + (window.outerHeight - height) / 2;
          const popup = window.open(
            data.authUrl,
            'Google Sign In',
            `width=${width},height=${height},left=${left},top=${top},toolbar=0,location=0,menubar=0,status=0`
          );
          setAuthWindow(popup);
        }
      }
    } catch (error) {
      console.error('Error initiating Google login:', error);
    }
  };

  const handleGuestLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (guestName.trim()) {
      const guestId = `guest_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      onLogin(guestId, true, guestName);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md w-96">
        <h1 className="text-2xl font-bold text-center mb-6">Welcome to Athen</h1>
        
        {error && (
          <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
            {error}
          </div>
        )}
        
        {!showGuestForm ? (
          <div className="space-y-4">
            <button
              onClick={handleGoogleLogin}
              className="w-full flex items-center justify-center gap-2 bg-white border border-gray-300 rounded-lg px-4 py-2 text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <FcGoogle className="text-xl" />
              Continue with Google
            </button>
            
            <button
              onClick={() => setShowGuestForm(true)}
              className="w-full flex items-center justify-center gap-2 bg-gray-800 text-white rounded-lg px-4 py-2 hover:bg-gray-700 transition-colors"
            >
              <FaUser />
              Continue as Guest
            </button>
          </div>
        ) : (
          <form onSubmit={handleGuestLogin} className="space-y-4">
            <div>
              <label htmlFor="guestName" className="block text-sm font-medium text-gray-700 mb-1">
                Enter your name
              </label>
              <input
                type="text"
                id="guestName"
                value={guestName}
                onChange={(e) => setGuestName(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Your name"
                required
              />
            </div>
            
            <button
              type="submit"
              className="w-full bg-blue-600 text-white rounded-lg px-4 py-2 hover:bg-blue-700 transition-colors"
            >
              Continue
            </button>
            
            <button
              type="button"
              onClick={() => setShowGuestForm(false)}
              className="w-full text-gray-600 text-sm hover:text-gray-800"
            >
              Back to login options
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

export default LoginPage; 