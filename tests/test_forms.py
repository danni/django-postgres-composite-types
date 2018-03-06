"""Tests for CompositeTypeField and CompositeTypeWidget."""
import datetime

from django import forms
from django.test import SimpleTestCase
from django.test.testcases import assert_and_parse_html

from postgres_composite_types.forms import CompositeTypeField

from .test_field import SimpleType


class TestField(SimpleTestCase):
    """
    Test the CompositeTypeField
    """

    class SimpleForm(forms.Form):
        """Test form with CompositeTypeField"""
        simple_field = CompositeTypeField(model=SimpleType)

    simple_valid_data = {
        'simple_field-a': '1',
        'simple_field-b': 'foo',
        'simple_field-c': '2016-05-24 17:38:32',
    }

    def test_composite_field(self):
        """Test that a composite field can create an instance of its model"""

        form = self.SimpleForm(data=self.simple_valid_data)

        self.assertTrue(form.is_valid())

        out = form.cleaned_data['simple_field']
        self.assertIsInstance(out, SimpleType)
        self.assertEqual(out, SimpleType(
            a=1, b='foo', c=datetime.datetime(2016, 5, 24, 17, 38, 32)))

    def test_validation(self):
        """
        Test that a composite field validates its input, throwing errors for
        bad data
        """
        form = self.SimpleForm(data={
            'simple_field-a': 'one',
            'simple_field-b': '',
            'simple_field-c': 'yesterday, 10 oclock',
        })
        # CompositeTypeFields should fail validation if any of their fields
        # fail validation
        self.assertFalse(form.is_valid())
        self.assertIn('simple_field', form.errors)
        # All three fields should be incorrect
        self.assertEqual(len(form.errors['simple_field']), 3)
        # Errors should be formatted like 'Label: Error message'
        self.assertEqual(str(form.errors['simple_field'][0]),
                         'A number: Enter a whole number.')

        # Fields with validation errors should render with their invalid input
        self.assertHTMLContains(
            """
            <input id="id_simple_field-a" name="simple_field-a"
                placeholder="A number" required type="number" value="one" />
            """,
            str(form['simple_field']))

    def test_subfield_validation(self):
        """Errors on subfields should be accessible"""
        form = self.SimpleForm(data={
            'simple_field-a': 'one',
        })
        self.assertFalse(form.is_valid())
        self.assertEqual(str(form['simple_field']['a'].errors[0]),
                         'Enter a whole number.')

    def test_subfields(self):
        """Test accessing bound subfields"""
        form = self.SimpleForm(data=self.simple_valid_data)
        a_bound_field = form['simple_field']['a']

        self.assertIsInstance(a_bound_field.field, forms.IntegerField)
        self.assertEqual(a_bound_field.html_name, 'simple_field-a')

    def test_nested_prefix(self):
        """Test forms with a prefix"""
        form = self.SimpleForm(data=self.simple_valid_data, prefix='step1')

        composite_bound_field = form['simple_field']
        self.assertEqual(composite_bound_field.html_name,
                         'step1-simple_field')

        a_bound_field = composite_bound_field['a']
        self.assertEqual(a_bound_field.html_name,
                         'step1-simple_field-a')

    def test_initial_data(self):
        """
        Check that forms with initial data render with the fields prepopulated.
        """
        initial = SimpleType(
            a=1, b='foo', c=datetime.datetime(2016, 5, 24, 17, 38, 32))
        form = self.SimpleForm(initial={'simple_field': initial})

        self.assertHTMLContains(
            """
            <input id="id_simple_field-a" name="simple_field-a"
                placeholder="A number" required type="number" value="1" />
            """,
            str(form['simple_field']))

    # pylint:disable=invalid-name
    def assertHTMLContains(self, text, content, count=None, msg=None):
        """
        Assert that the HTML snippet ``text`` is found within the HTML snippet
        ``content``. Like assertContains, but works with plain strings instead
        of Response instances.
        """
        content = assert_and_parse_html(
            self, content, None, "HTML content to search in is not valid:")
        text = assert_and_parse_html(
            self, text, None, "HTML content to search for is not valid:")

        matches = content.count(text)
        if count is None:
            self.assertTrue(
                matches > 0, msg=msg or 'Could not find HTML snippet')
        else:
            self.assertEqual(
                matches, count,
                msg=msg or 'Found %d matches, expecting %d' % (matches, count))


class OptionalFieldTests(SimpleTestCase):
    """
    CompundTypeFields should handle being optional sensibly
    """
    class OptionalSimpleForm(forms.Form):
        """Test form with optional CompositeTypeField"""
        optional_field = CompositeTypeField(model=SimpleType, required=False)

    simple_valid_data = {
        'optional_field-a': '1',
        'optional_field-b': 'foo',
        'optional_field-c': '2016-05-24 17:38:32',
    }

    def test_blank_fields(self):
        """Test leaving all the fields blank"""

        form = self.OptionalSimpleForm(data={
            'simple_field-a': '',
            'simple_field-b': '',
            'simple_field-c': '',
        })

        # The form should be valid, but simple_field should be None
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data['optional_field'])

    def test_missing_fields(self):
        """Test not even submitting the fields"""

        form = self.OptionalSimpleForm(data={})

        # The form should be valid, but simple_field should be None
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data['optional_field'])

    def test_filling_out_fields(self):
        """Test filling out the fields normally still works"""

        form = self.OptionalSimpleForm(data=self.simple_valid_data)

        self.assertTrue(form.is_valid())
        out = form.cleaned_data['optional_field']
        self.assertIsInstance(out, SimpleType)
        self.assertEqual(out, SimpleType(
            a=1, b='foo', c=datetime.datetime(2016, 5, 24, 17, 38, 32)))

    def test_some_valid_some_empty(self):
        """Test with some fields filled in, some required fields blank"""

        form = self.OptionalSimpleForm(data={
            'optional_field-a': '1',
            'optional_field-b': 'foo',
            'optional_field-c': '',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('optional_field', form.errors)
        # Only the one field should fail validation
        self.assertEqual(len(form.errors['optional_field']), 1)
        # Errors should be formatted like 'Label: Error message'
        self.assertEqual('A date: This field is required.',
                         str(form.errors['optional_field'][0]))
