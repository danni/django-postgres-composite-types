# pylint:disable=invalid-name
"""
Migration to create custom types
"""

from django.db import migrations

from ..base import SimpleType


class Migration(migrations.Migration):
    """Migration."""

    dependencies = [
    ]

    operations = [
        SimpleType.Operation(),
    ]
