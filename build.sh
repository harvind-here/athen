#!/usr/bin/env bash

# Exit on error
set -o errexit

# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt-get install -y nodejs

# Build Frontend
cd frontend
npm install
npm run build
cd ..

# Install Python dependencies
pip install -r requirements.txt

# Start the Flask server
python app.py 