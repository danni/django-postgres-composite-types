"""
Custom fields for the tests.
"""

from django.db import models


class TripleOnAssignDescriptor:
    """A descriptor that multiplies the assigned value by 3."""
    def __init__(self, field):
        self.field = field

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return instance.__dict__[self.field.name]

    def __set__(self, instance, value):
        # Allow NULL
        if value is not None:
            value *= 3
        instance.__dict__[self.field.name] = value


class TriplingIntegerField(models.IntegerField):
    """Field that triples assigned value."""
    # pylint:disable=arguments-differ
    def contribute_to_class(self, cls, name, **kwargs):
        super().contribute_to_class(cls, name, **kwargs)
        setattr(cls, self.name, TripleOnAssignDescriptor(self))
