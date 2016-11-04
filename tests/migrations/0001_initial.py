# pylint:disable=invalid-name
"""
Migration to create custom types
"""

from django.db import migrations

from ..base import Box, Card, DateRange, OptionalBits, Point, SimpleType


class Migration(migrations.Migration):
    """Migration."""

    dependencies = [
    ]

    operations = [
        SimpleType.Operation(),
        OptionalBits.Operation(),
        Card.Operation(),
        Point.Operation(),
        Box.Operation(),
        DateRange.Operation(),
    ]
