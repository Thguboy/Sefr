"""
PythonAnywhere WSGI entry point.

In PythonAnywhere Web tab → Code → WSGI configuration file,
paste the contents of THIS file (or point the WSGI file path here).

Replace <username> with your actual PythonAnywhere username.
"""

import sys
import os

# Add the project directory to sys.path
path = '/home/<username>/Sefr'
if path not in sys.path:
    sys.path.insert(0, path)

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(path, '.env'))
except ImportError:
    pass

from app import application  # noqa: E402 — 'application' is the WSGI callable
