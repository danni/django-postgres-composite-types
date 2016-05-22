# pylint:disable=invalid-name
"""
Migration to create custom types
"""

from django.db import migrations
from ..test_field import TestType


class Migration(migrations.Migration):
    """Migration."""

    dependencies = [
    ]

    operations = [
        TestType.Operation(),
    ]
