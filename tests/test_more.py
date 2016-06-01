"""
Tests for composite fields in combination with other interesting fields.
"""

from django.test import TestCase

from .base import Box, Card, Hand, Item, Point


@Hand.fake_me
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
        hand.save()  # pylint:disable=no-member

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
        hand.save()  # pylint:disable=no-member

        queen_of_hearts = Card('♡', 'Q')
        jack_of_spades = Card('♠', 'J')
        self.assertTrue(
            Hand.objects.filter(cards__contains=[queen_of_hearts]).exists())
        self.assertFalse(
            Hand.objects.filter(cards__contains=[jack_of_spades]).exists())


@Item.fake_me
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
        item.save()  # pylint:disable=no-member

        item = Item.objects.get()
        self.assertEqual(item.name, "table")
        self.assertEqual(item.bounding_box,
                         Box(top_left=Point(x=1, y=1),
                             bottom_right=Point(x=4, y=2)))

        self.assertEqual(item.bounding_box.bottom_left,
                         Point(x=1, y=2))
        self.assertEqual(item.bounding_box.top_right,
                         Point(x=4, y=1))
