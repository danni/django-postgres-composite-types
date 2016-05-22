"""Tests for composite field."""

import datetime

from django.db import models, connection
from django.test import TestCase, TransactionTestCase
from django.db.migrations.executor import MigrationExecutor


from django_fake_model.models import FakeModel

from postgres_composite_types import CompositeType


class TestType(CompositeType):
    """A test type."""
    # pylint:disable=invalid-name
    a = models.IntegerField()
    b = models.CharField(max_length=32)
    c = models.DateTimeField()

    class Meta:
        db_type = 'test_type'


class TestModel(FakeModel):
    """A test model."""
    # pylint:disable=invalid-name
    a = TestType.Field()

    class Meta:
        app_label = 'test'


class TestMigrations(TransactionTestCase):
    """
    Taken from
    https://www.caktusgroup.com/blog/2016/02/02/writing-unit-tests-django-migrations/

    FIXME: the ordering of the tests is totally broken.
    """

    @property
    def app(self):
        """App."""
        from django.apps import apps

        return apps.get_containing_app_config(type(self).__module__).name

    migrate_to = '0001_initial'

    def test_migration(self):
        """Data data migration."""
        from django.apps import apps

        # cursor = connection.connection.cursor()
        # cursor.execute("DELETE FROM django_migrations WHERE app='tests'")
        # cursor.execute("DROP TYPE IF EXISTS test_type")

        self.migrate_to = [(self.app, self.migrate_to)]
        executor = MigrationExecutor(connection)

        # Run the migration to test
        executor.migrate(self.migrate_to)

        self.apps = executor.loader.project_state(self.migrate_to).apps

        super().setUp()


@TestModel.fake_me
class FieldTests(TestCase):
    """Tests for composite field."""

    def test_field_save_and_load(self):
        """Save and load a test model."""
        # pylint:disable=invalid-name
        t = TestType(a=1, b="b", c=datetime.datetime(1985, 10, 26, 9, 0))
        m = TestModel(a=t)
        m.save()  # pylint:disable=no-member

        # Retrieve from DB
        m = TestModel.objects.get(id=1)
        self.assertIsNotNone(m.a)
        self.assertIsInstance(m.a, TestType)
        self.assertEqual(m.a.a, 1)
        self.assertEqual(m.a.b, "b")
        self.assertEqual(m.a.c, datetime.datetime(1985, 10, 26, 9, 0))

        cursor = connection.connection.cursor()
        cursor.execute("SELECT (a).a FROM test_testmodel")
        result, = cursor.fetchone()
        print(result)

        self.assertEqual(result, 1)

        cursor = connection.connection.cursor()
        cursor.execute("SELECT (a).b FROM test_testmodel")
        result, = cursor.fetchone()
        print(result)

        self.assertEqual(result, "b")
