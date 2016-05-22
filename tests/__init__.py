"""
Tests.
"""

# Set up Django
import os

os.environ['DJANGO_SETTINGS_MODULE'] = 'tests.settings'

# pylint:disable=wrong-import-position
import django  # noqa

django.setup()
