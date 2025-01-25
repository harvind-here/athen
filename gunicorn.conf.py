import os

# Bind to 0.0.0.0 to accept all incoming connections
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# Worker configuration
workers = 4  # Generally (2 x num_cores) + 1
worker_class = 'gevent'
threads = 2
timeout = 120

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Enable when using Flask debug mode
reload = False 