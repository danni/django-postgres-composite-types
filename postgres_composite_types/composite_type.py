import logging

from django.db import connections, models
from django.db.backends.signals import connection_created
from django.db.models.base import ModelBase
from django.db.models.manager import EmptyManager
from django.db.models.signals import post_migrate
from psycopg2 import ProgrammingError
from psycopg2.extensions import ISQLQuote, register_adapter
from psycopg2.extras import CompositeCaster, register_composite

from .fields import BaseField, DummyField
from .quoting import QuotedCompositeType

LOGGER = logging.getLogger(__name__)

__all__ = ["CompositeType"]


class CompositeTypeMeta(ModelBase):
    """Metaclass for Type."""

    @classmethod
    def __prepare__(cls, name, bases):
        """
        Guarantee the ordering of the declared attrs.

        We need this so that our type doesn't change ordering between
        invocations.
        """
        return {}

    def __new__(cls, name, bases, attrs):
        # Only apply the metaclass to our subclasses
        if name == "CompositeType":
            return super().__new__(cls, name, bases, attrs)

        # retrieve any fields from our declaration
        fields = []
        for field_name, value in attrs.copy().items():
            if isinstance(value, models.fields.related.RelatedField):
                raise TypeError("Composite types cannot contain " "related fields")

            if isinstance(value, models.Field):
                field = attrs[field_name]
                field.set_attributes_from_name(field_name)
                fields.append((field_name, field))

        # retrieve the Meta from our declaration
        try:
            meta_obj = attrs["Meta"]
        except KeyError as exc:
            raise TypeError(f'{name} has no "Meta" class') from exc

        try:
            meta_obj.db_table
        except AttributeError as exc:
            raise TypeError(f"{name}.Meta.db_table is required.") from exc

        # create the field for this Type
        attrs["Field"] = type(f"{name}.Field", (BaseField,), {})

        attrs["__id"] = DummyField(primary_key=True, serialize=False)
        attrs["__id"].name = "pk"

        # Use an EmptyManager for everything as types cannot be queried.
        meta_obj.default_manager_name = "objects"
        meta_obj.base_manager_name = "objects"
        attrs["objects"] = EmptyManager(model=None)

        ret = super().__new__(cls, name, bases, attrs)
        ret.Field._composite_type_model = ret
        return ret

    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        if name == "CompositeType":
            return

        cls._connect_signals()

    def _on_signal_register_type(cls, signal, sender, connection=None, **kwargs):
        """
        Attempt registering the type after a migration succeeds.
        """
        from django.db.backends.postgresql.base import DatabaseWrapper

        if connection is None:
            connection = connections["default"]

        if isinstance(connection, DatabaseWrapper):
            # On-connect, register the QuotedCompositeType with psycopg2.
            # This is what to do when the type is going in to the database
            register_adapter(cls, QuotedCompositeType)

            # Now try to register the type. If the type has not been created
            # in a migration, the registration will fail. The type will be
            # registered as part of the migration, so hopefully the migration
            # will run soon.

            try:
                cls.register_composite(connection)
            except ProgrammingError as exc:
                LOGGER.warning(
                    "Failed to register composite %r. "
                    "The migration to register it may not have run yet. "
                    "Error details: %s",
                    cls.__name__,
                    exc,
                )
            else:
                # Registration succeeded.Disconnect the signals now.
                cls._disconnect_signals()

    def _connect_signals(cls):
        type_id = cls._meta.db_table

        # Register the type on the first database connection
        connection_created.connect(
            receiver=cls._on_signal_register_type, dispatch_uid=f"connect:{type_id}"
        )

        # Also register on post-migrate.
        # This ensures that, if the on-connect signal failed due to a migration
        # not having run yet, running the migration will still register it,
        # even if in the same session (this can happen in tests for example).
        # dispatch_uid needs to be distinct from the one on connection_created.
        post_migrate.connect(
            receiver=cls._on_signal_register_type,
            dispatch_uid=f"post_migrate:{type_id}",
        )

    def _disconnect_signals(cls):
        type_id = cls._meta.db_table
        connection_created.disconnect(
            cls._on_signal_register_type, dispatch_uid=f"connect:{type_id}"
        )
        post_migrate.disconnect(
            cls._on_signal_register_type, dispatch_uid=f"post_migrate:{type_id}"
        )


class CompositeType(metaclass=CompositeTypeMeta):
    """
    A new composite type stored in Postgres.
    """

    # The database connection this type is registered with
    registered_connection = None

    def __init__(self, *args, **kwargs):
        if args and kwargs:
            raise RuntimeError("Specify either args or kwargs but not both.")

        for field in self._meta.fields:
            setattr(self, field.name, None)

        # Unpack any args as if they came from the type
        for field, arg in zip(self._meta.fields, args):
            setattr(self, field.name, arg)

        for name, value in kwargs.items():
            setattr(self, name, value)

    def __repr__(self):
        args = ", ".join(f"{k}={v}" for k, v in self.__to_dict__().items())
        return f"<{type(self).__name__}({args})>"

    def __to_tuple__(self):
        return tuple(
            field.get_prep_value(getattr(self, field.name))
            for field in self._meta.fields
        )

    def __to_dict__(self):
        return {
            field.name: field.get_prep_value(getattr(self, field.name))
            for field in self._meta.fields
        }

    def __eq__(self, other):
        if not isinstance(other, CompositeType):
            return False
        if self._meta.model != other._meta.model:
            return False
        for field in self._meta.fields:
            if getattr(self, field.name) != getattr(other, field.name):
                return False
        return True

    @classmethod
    def register_composite(cls, connection):
        """
        Register this CompositeType with Postgres.

        If the CompositeType does not yet exist in the database, this will
        fail.  Hopefully a migration will come along shortly and create the
        type in the database. If `retry` is True, this CompositeType will try
        to register itself again after the type is created.
        """

        LOGGER.debug(
            "Registering composite type %s on connection %s", cls.__name__, connection
        )
        cls.registered_connection = connection

        with connection.temporary_connection() as cur:
            # This is what to do when the type is coming out of the database
            register_composite(
                cls._meta.db_table, cur, globally=True, factory=cls.Caster
            )

    def __conform__(self, protocol):
        """
        CompositeTypes know how to conform to the ISQLQuote protocol, by
        wrapping themselves in a QuotedCompositeType. The ISQLQuote protocol
        is all about formatting custom types for use in SQL statements.

        Returns None if it can not conform to the requested protocol.
        """
        if protocol is ISQLQuote:
            return QuotedCompositeType(self)

        return None

    class Field(BaseField):
        """
        Placeholder for the field that will be produced for this type.
        """

    class Caster(CompositeCaster):
        """
        Placeholder for the caster that will be produced for this type
        """

    def _get_next_or_previous_by_FIELD(self):
        pass

    @classmethod
    def check(cls, **kwargs):
        return []
