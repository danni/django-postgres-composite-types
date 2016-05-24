"""Tests for composite field."""

import datetime
from unittest import mock

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from postgres_composite_types import composite_type_created

from .base import SimpleModel, SimpleType


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


@SimpleModel.fake_me
class FieldTests(TestCase):
    """Tests for composite field."""

    def test_field_save_and_load(self):
        """Save and load a test model."""
        # pylint:disable=invalid-name
        t = SimpleType(a=1, b="b", c=datetime.datetime(1985, 10, 26, 9, 0))
        m = SimpleModel(test_field=t)
        m.save()  # pylint:disable=no-member

        # Retrieve from DB
        m = SimpleModel.objects.get(id=1)
        self.assertIsNotNone(m.test_field)
        self.assertIsInstance(m.test_field, SimpleType)
        self.assertEqual(m.test_field.a, 1)
        self.assertEqual(m.test_field.b, "b")
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

        self.assertEqual(result, "b")
