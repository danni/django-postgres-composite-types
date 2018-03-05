"""Tests for composite field."""

import datetime
import json
from unittest import mock

from django.core import serializers
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from psycopg2.extensions import adapt

from postgres_composite_types import composite_type_created

from .models import (
    Box, DateRange, Item, NamedDateRange, OptionalBits, OptionalModel, Point,
    SimpleModel, SimpleType)


class TestMigrations(TransactionTestCase):
    """
    Taken from
    https://www.caktusgroup.com/blog/2016/02/02/writing-unit-tests-django-migrations/

    FIXME: the ordering of the tests is totally broken.
    """

    app = 'tests'
    migrate_from = [('tests', None)]  # Before the first migration
    migrate_to = [('tests', '0001_initial')]

    def does_type_exist(self, type_name):
        """
        Check if a composite type exists in the database
        """
        sql = 'select exists (select 1 from pg_type where typname = %s);'
        with connection.cursor() as cursor:
            cursor.execute(sql, [type_name])
            row = cursor.fetchone()
            return row[0]

    def migrate(self, targets):
        """
        Migrate to a new state.

        MigrationExecutors can not be reloaded, as they cache the state of the
        migrations when created. Attempting to reuse one might make some
        migrations not run, as it thinks they have already been run.
        """
        executor = MigrationExecutor(connection)
        executor.migrate(targets)

        # Cant load state for apps in the initial empty state
        state_nodes = [node for node in targets if node[1] is not None]
        return executor.loader.project_state(state_nodes).apps

    def test_migration(self):
        """Data data migration."""

        # The migrations have already been run, and the type already exists in
        # the database
        self.assertTrue(self.does_type_exist(SimpleType._meta.db_type))

        # Run the migration backwards to check the type is deleted
        self.migrate(self.migrate_from)

        # The type should now not exist
        self.assertFalse(self.does_type_exist(SimpleType._meta.db_type))

        # A signal is fired when the migration creates the type
        signal_func = mock.Mock()
        composite_type_created.connect(receiver=signal_func, sender=SimpleType)

        # Run the migration forwards to create the type again
        self.migrate(self.migrate_to)

        # The signal should have been sent
        self.assertEqual(signal_func.call_count, 1)
        self.assertEqual(signal_func.call_args, ((), {
            'sender': SimpleType,
            'signal': composite_type_created,
            'connection': connection}))

        # The type should now exist again
        self.assertTrue(self.does_type_exist(SimpleType._meta.db_type))

    def test_migration_quoting(self):
        """Test that migration SQL is generated with correct quoting"""

        # The migrations have already been run, and the type already exists in
        # the database
        self.migrate(self.migrate_to)
        self.assertTrue(self.does_type_exist(DateRange._meta.db_type))


class FieldTests(TestCase):
    """Tests for composite field."""

    def test_field_save_and_load(self):
        """Save and load a test model."""
        # pylint:disable=invalid-name
        t = SimpleType(a=1, b="β ☃", c=datetime.datetime(1985, 10, 26, 9, 0))
        m = SimpleModel(test_field=t)
        m.save()

        # Retrieve from DB
        m = SimpleModel.objects.get(id=1)
        self.assertIsNotNone(m.test_field)
        self.assertIsInstance(m.test_field, SimpleType)
        self.assertEqual(m.test_field.a, 1)
        self.assertEqual(m.test_field.b, "β ☃")
        self.assertEqual(m.test_field.c, datetime.datetime(1985, 10, 26, 9, 0))

        cursor = connection.connection.cursor()
        cursor.execute("SELECT (test_field).a FROM %s" % (
            SimpleModel._meta.db_table,))
        result, = cursor.fetchone()

        self.assertEqual(result, 1)

        cursor = connection.connection.cursor()
        cursor.execute("SELECT (test_field).b FROM %s" % (
            SimpleModel._meta.db_table,))
        result, = cursor.fetchone()

        self.assertEqual(result, "β ☃")

    def test_field_save_and_load_with_reserved_names(self):
        """Test save/load of a composite type with reserved field names"""
        start = datetime.datetime.now()
        end = datetime.datetime.now() + datetime.timedelta(days=1)
        date_range = DateRange(start=start, end=end)
        model = NamedDateRange(name='foobar', date_range=date_range)
        model.save()

        model = NamedDateRange.objects.get()
        self.assertEqual(model.date_range, date_range)

    def test_adapted_sql(self):
        """
        Check that the value is serialised to the correct SQL string, including
        a type cast
        """
        value = SimpleType(a=1, b="b", c=datetime.datetime(1985, 10, 26, 9, 0))

        adapted = adapt(value)
        adapted.prepare(connection.connection)

        self.assertEqual(
            b"(1, 'b', '1985-10-26T09:00:00'::timestamp)::test_type",
            adapted.getquoted())

    def test_serialize(self):
        """
        Check that composite values are correctly handled through Django's
        serialize/deserialize helpers, used for dumpdata/loaddata.
        """
        old = Item(
            name="table",
            bounding_box=Box(top_left=Point(x=1, y=1),
                             bottom_right=Point(x=4, y=2)))
        out = serializers.serialize("json", [old])
        new = next(serializers.deserialize("json", out)).object

        self.assertEqual(old.bounding_box,
                         new.bounding_box)

    def test_to_python(self):
        """
        Test the Field.to_python() method interprets strings as JSON data.
        """
        start = datetime.datetime.now()
        end = datetime.datetime.now() + datetime.timedelta(days=1)

        field = NamedDateRange._meta.get_field('date_range')
        out = field.to_python(json.dumps({
            "start": start.isoformat(),
            "end": end.isoformat(),
        }))

        self.assertEqual(out, DateRange(start=start, end=end))

    def test_to_python_bad_json(self):
        """
        Test the Field.to_python() handles bad JSON data by raising
        a ValidationError
        """
        field = NamedDateRange._meta.get_field('date_range')

        with self.assertRaises(ValidationError) as context:
            field.to_python("bogus JSON")

        exception = context.exception
        self.assertEqual(exception.code, 'bad_json')


class TestOptionalFields(TestCase):
    """
    Test optional composite type fields, and optional fields on composite types
    """

    def test_null_field_save_and_load(self):
        """Save and load a null composite field"""
        model = OptionalModel(optional_field=None)
        model.save()

        model = OptionalModel.objects.get()
        self.assertIsNone(model.optional_field)

    def test_null_subfield_save_and_load(self):
        """Save and load a null composite field"""
        model = OptionalModel(optional_field=OptionalBits(
            required='foo', optional=None))
        model.save()

        model = OptionalModel.objects.get()
        self.assertIsNotNone(model.optional_field)
        self.assertEqual(model.optional_field, OptionalBits(
            required='foo', optional=None))

    def test_all_filled(self):
        """
        Save and load an optional composite field with all its optional fields
        filled in
        """
        model = OptionalModel(optional_field=OptionalBits(
            required='foo', optional='bar'))
        model.save()

        model = OptionalModel.objects.get(id=1)
        self.assertIsNotNone(model.optional_field)
        self.assertEqual(model.optional_field, OptionalBits(
            required='foo', optional='bar'))
