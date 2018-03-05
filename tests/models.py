"""Models and types for the tests"""
from django.contrib.postgres.fields.array import ArrayField
from django.db import models

from postgres_composite_types import CompositeType

from .fields import TriplingIntegerField


class SimpleType(CompositeType):
    """A test type."""
    class Meta:
        db_type = 'test_type'

    # pylint:disable=invalid-name
    a = models.IntegerField(verbose_name='A number')
    b = models.CharField(verbose_name='A name', max_length=32)
    c = models.DateTimeField(verbose_name='A date')


class SimpleModel(models.Model):
    """A test model."""
    # pylint:disable=invalid-name
    test_field = SimpleType.Field()


class OptionalBits(CompositeType):
    """A type with an optional field"""
    required = models.CharField(max_length=32)
    optional = models.CharField(max_length=32, null=True, blank=True)

    class Meta:
        db_type = 'optional_type'


class OptionalModel(models.Model):
    """A model with an optional composity type"""
    optional_field = OptionalBits.Field(null=True, blank=True)


class Card(CompositeType):
    """A playing card."""
    class Meta:
        db_type = 'card'

    suit = models.CharField(max_length=1)
    rank = models.CharField(max_length=2)


class Hand(models.Model):
    """A hand of cards."""
    cards = ArrayField(base_field=Card.Field())


class Point(CompositeType):
    """A point on the cartesian plane."""
    class Meta:
        db_type = 'test_point'  # Postgres already has a point type

    # pylint:disable=invalid-name
    x = models.IntegerField()
    y = models.IntegerField()


class Box(CompositeType):
    """An axis-aligned box on the cartesian plane."""
    class Meta:
        db_type = 'test_box'  # Postgres already has a box type

    top_left = Point.Field()
    bottom_right = Point.Field()

    @property
    def bottom_left(self):
        """The bottom-left corner of the box."""
        # pylint:disable=no-member
        return Point(x=self.top_left.x,
                     y=self.bottom_right.y)

    @property
    def top_right(self):
        """The top-right corner of the box."""
        # pylint:disable=no-member
        return Point(x=self.bottom_right.x,
                     y=self.top_left.y)


class Item(models.Model):
    """An item that exists somewhere on a cartesian plane."""
    name = models.CharField(max_length=20)
    bounding_box = Box.Field()


class DateRange(CompositeType):
    """A date range with start and end."""
    class Meta:
        db_type = 'test_date_range'

    start = models.DateTimeField()
    end = models.DateTimeField()   # uses reserved keyword


class NamedDateRange(models.Model):
    """A date-range with a name"""
    name = models.TextField()
    date_range = DateRange.Field()


class DescriptorType(CompositeType):
    """Has a field implementing a custom descriptor"""
    class Meta:
        db_type = 'test_custom_descriptor'

    value = TriplingIntegerField()


class DescriptorModel(models.Model):
    """Has a composite type with a field implementing a custom descriptor"""
    field = DescriptorType.Field()
