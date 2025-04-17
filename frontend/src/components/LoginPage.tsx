import React, { useState, useEffect, useCallback } from 'react';
import { FcGoogle } from 'react-icons/fc';
import { FaUser } from 'react-icons/fa';
import { motion } from 'framer-motion';
import './LoginPage.css';

interface LoginPageProps {
  onLogin: (userId: string, isGuest: boolean, name?: string) => void;
  error?: string | null;
}

const LoginPage: React.FC<LoginPageProps> = ({ onLogin, error }) => {
  const [guestName, setGuestName] = useState('');
  const [showGuestForm, setShowGuestForm] = useState(false);
  const [authWindow, setAuthWindow] = useState<Window | null>(null);

  const checkAuthStatus = useCallback(async () => {
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
  }, [onLogin]);

  useEffect(() => {
    checkAuthStatus();
  }, [checkAuthStatus]);

  useEffect(() => {
    if (!authWindow) return;

    const checkPopup = setInterval(async () => {
      if (authWindow.closed) {
        clearInterval(checkPopup);
        setAuthWindow(null);

        setTimeout(async () => {
          await checkAuthStatus();
        }, 1000);
      }
    }, 500);

    return () => clearInterval(checkPopup);
  }, [authWindow, checkAuthStatus]);

  const handleGoogleLogin = async () => {
    try {
      const response = await fetch('/api/auth/google', {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`API request failed: ${response.statusText}`);
      }

      const data = await response.json();

      if (data.authUrl) {
        console.log("Authentication required, opening popup.");
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
      } else if (data.message === "Already authenticated" && data.user) {
        console.log("Already authenticated on backend, logging in.");
        onLogin(data.user.id, data.user.isGuest, data.user.name);
      } else {
        console.error('Unexpected response from /api/auth/google:', data);
      }

    } catch (error) {
      console.error('Error during Google login process:', error);
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
    <div className="login-wrapper">
    <div className="min-h-screen flex items-center justify-center p-4 overflow-hidden bg-gray-100 dark:bg-gray-900">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="login-card shadow-lg w-full max-w-md border"
      >
        <motion.h1
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="text-3xl font-bold text-center mb-8"
        >
          Welcome to ATHEN
        </motion.h1>

        {error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="mb-6 p-3 rounded-lg text-sm login-error"
          >
            {error}
          </motion.div>
        )}

        {!showGuestForm ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3, duration: 0.5 }}
            className="space-y-5"
          >
            <motion.button
              whileHover={{ scale: 1.03, transition: { duration: 0.15 } }}
              whileTap={{ scale: 0.98 }}
              onClick={handleGoogleLogin}
              className="login-button"
            >
              <FcGoogle className="text-2xl" />
              Continue with Google
            </motion.button>

            <motion.button
              whileHover={{ scale: 1.03, transition: { duration: 0.15 } }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setShowGuestForm(true)}
              className="login-button"
            >
              <FaUser />
              Continue as Guest
            </motion.button>
          </motion.div>
        ) : (
          <motion.form
            initial={{ opacity: 0, x: 50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3 }}
            onSubmit={handleGuestLogin}
            className="space-y-5"
          >
            <div>
              <label htmlFor="guestName" className="block text-sm font-medium mb-1">
                Enter your name
              </label>
              <input
                type="text"
                id="guestName"
                value={guestName}
                onChange={(e) => setGuestName(e.target.value)}
                className="login-input"
                placeholder="Your name"
                required
              />
            </div>
            

            <motion.button
              whileHover={{ scale: 1.03, transition: { duration: 0.15 } }}
              whileTap={{ scale: 0.98 }}
              type="submit"
              className="login-button"
            >
              Continue
            </motion.button>

            <motion.button
              whileHover={{ scale: 1.03, transition: { duration: 0.15 } }}
              whileTap={{ scale: 0.98 }}
              type="button"
              onClick={() => setShowGuestForm(false)}
              className="w-full text-center text-sm hover:underline focus:outline-none"
            >
              Back
            </motion.button>
          </motion.form>
        )}
      </motion.div>
    </div>
    </div>
  );
};

export default LoginPage;
