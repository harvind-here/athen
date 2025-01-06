export const handleGoogleAuth = (authUrl) => {
  // Open the auth URL in a new window
  const authWindow = window.open(
    authUrl,
    'Google Calendar Authentication',
    'width=600,height=600'
  );

  // Handle the window close event
  const checkWindow = setInterval(() => {
    if (authWindow.closed) {
      clearInterval(checkWindow);
      // Check authentication status
      fetch('/api/auth_status')
        .then(response => response.json())
        .then(data => {
          if (data.authenticated) {
            // Optionally show success message
            alert('Authentication successful!');
          } else {
            // Optionally show error message
            alert('Authentication failed or was cancelled.');
          }
        })
        .catch(error => {
          console.error('Error checking auth status:', error);
          alert('Error checking authentication status.');
        });
    }
  }, 500);
}; 