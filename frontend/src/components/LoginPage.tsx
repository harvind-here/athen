import React from 'react';
import { FcGoogle } from 'react-icons/fc';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import './LoginPage.css';

interface LoginPageProps {
  error?: string | null;
}

const LoginPage: React.FC<LoginPageProps> = ({ error }) => {
  const { handleGoogleSignIn } = useAuth();

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

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3, duration: 0.5 }}
            className="space-y-5"
          >
            <motion.button
              whileHover={{ scale: 1.03, transition: { duration: 0.15 } }}
              whileTap={{ scale: 0.98 }}
              onClick={handleGoogleSignIn}
              className="login-button"
            >
              <FcGoogle className="text-2xl" />
              Continue with Google
            </motion.button>
          </motion.div>
        </motion.div>
      </div>
    </div>
  );
};

export default LoginPage;
