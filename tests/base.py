"""Models and types for the tests"""
from django.db import models
from django_fake_model.models import FakeModel

from postgres_composite_types import CompositeType


class SimpleType(CompositeType):
    """A test type."""
    class Meta:
        db_type = 'test_type'

    # pylint:disable=invalid-name
    a = models.IntegerField(verbose_name='A number')
    b = models.CharField(verbose_name='A name', max_length=32)
    c = models.DateTimeField(verbose_name='A date')


class SimpleModel(FakeModel):
    """A test model."""
    # pylint:disable=invalid-name
    test_field = SimpleType.Field()

    class Meta:
        app_label = 'test'
