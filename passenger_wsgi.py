"""Punto de entrada para cPanel → Setup Python App (Passenger)."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aircontrol.settings')

from aircontrol.wsgi import application  # noqa: E402,F401
