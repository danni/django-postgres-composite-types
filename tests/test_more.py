"""
Tests for composite fields in combination with other interesting fields.
"""

from django.db.migrations.writer import MigrationWriter
from django.test import TestCase

from .models import (
    Box, Card, DescriptorModel, DescriptorType, Hand, Item, Point)


class TestArrayFields(TestCase):
    """
    Test ArrayFields combined with CompositeType.Fields
    """

    def test_saving_and_loading_array_field(self):
        """
        Test saving and loading an ArrayField of a CompositeType
        """
        # Nice hand
        hand = Hand(cards=[
            Card('♡', '1'),
            Card('♡', 'K'),
            Card('♡', 'Q'),
            Card('♡', 'J'),
            Card('♡', '10'),
        ])
        hand.save()

        hand = Hand.objects.get()
        self.assertEqual(hand.cards, [
            Card('♡', '1'),
            Card('♡', 'K'),
            Card('♡', 'Q'),
            Card('♡', 'J'),
            Card('♡', '10'),
        ])

    def test_querying_array_field_contains(self):
        """
        Test using some array__contains=[CompositeType]
        """
        hand = Hand(cards=[
            Card('♡', '1'),
            Card('♡', 'K'),
            Card('♡', 'Q'),
            Card('♡', 'J'),
            Card('♡', '10'),
        ])
        hand.save()

        queen_of_hearts = Card('♡', 'Q')
        jack_of_spades = Card('♠', 'J')
        self.assertTrue(
            Hand.objects.filter(cards__contains=[queen_of_hearts]).exists())
        self.assertFalse(
            Hand.objects.filter(cards__contains=[jack_of_spades]).exists())

    def test_generate_migrations(self):
        """Test deconstruction of composite type as a base field"""
        field = Hand._meta.get_field('cards')
        text, _ = MigrationWriter.serialize(field)
        # build the expected full path of the nested composite type class
        models_module = Hand.__module__
        composite_field_cls = field.base_field.__class__.__name__
        expected_path = '.'.join((models_module, composite_field_cls))
        # check that the expected path is the one used by deconstruct
        expected_deconstruction = 'base_field={}()'.format(expected_path)
        self.assertIn(expected_deconstruction, text)


class TestNestedCompositeTypes(TestCase):
    """
    Test CompositeTypes within CompositeTypes
    """

    def test_saving_and_loading_nested_composite_types(self):
        """
        Test saving and loading an Item with nested CompositeTypes
        """
        item = Item(name="table",
                    bounding_box=Box(top_left=Point(x=1, y=1),
                                     bottom_right=Point(x=4, y=2)))
        item.save()

        item = Item.objects.get()
        self.assertEqual(item.name, "table")
        self.assertEqual(item.bounding_box,
                         Box(top_left=Point(x=1, y=1),
                             bottom_right=Point(x=4, y=2)))

        self.assertEqual(item.bounding_box.bottom_left,
                         Point(x=1, y=2))
        self.assertEqual(item.bounding_box.top_right,
                         Point(x=4, y=1))


class TestCustomDescriptors(TestCase):
    """
    Test CompositeTypes with Fields with custom descriptors.
    """

    def test_create(self):
        """Test descriptor used on creation"""
        model = DescriptorModel(field=DescriptorType(value=1))
        self.assertEqual(model.field.value, 3)

    def test_set(self):
        """Test descriptor used on assign"""
        model = DescriptorModel(field=DescriptorType(value=0))
        model.field.value = 14
        self.assertEqual(model.field.value, 42)
