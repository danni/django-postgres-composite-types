"""
Migration to create custom types
"""

from django.db import migrations

from ..models import (
    Box,
    Card,
    DateRange,
    DescriptorType,
    OptionalBits,
    Point,
    RenamedMemberType,
    SimpleType,
)


class Migration(migrations.Migration):
    """Migration."""

    dependencies = []

    operations = [
        SimpleType.Operation(),
        OptionalBits.Operation(),
        Card.Operation(),
        Point.Operation(),
        Box.Operation(),
        DateRange.Operation(),
        DescriptorType.Operation(),
        RenamedMemberType.Operation(),
    ]
