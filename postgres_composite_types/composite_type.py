import inspect
import logging
import sys

from django.db import models
from django.db.backends.postgresql.base import (
    DatabaseWrapper as PostgresDatabaseWrapper,
)
from django.db.backends.signals import connection_created
from psycopg2 import ProgrammingError
from psycopg2.extensions import ISQLQuote, register_adapter
from psycopg2.extras import CompositeCaster, register_composite

from .caster import BaseCaster
from .fields import BaseField
from .operations import BaseOperation
from .quoting import QuotedCompositeType

LOGGER = logging.getLogger(__name__)

__all__ = ["CompositeType"]


def _add_class_to_module(cls, module_name):
    cls.__module__ = module_name
    module = sys.modules[module_name]
    setattr(module, cls.__name__, cls)


class CompositeTypeMeta(type):
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
                field = attrs.pop(field_name)
                field.set_attributes_from_name(field_name)
                fields.append((field_name, field))

        # retrieve the Meta from our declaration
        try:
            meta_obj = attrs.pop("Meta")
        except KeyError as exc:
            raise TypeError(f'{name} has no "Meta" class') from exc

        try:
            meta_obj.db_type
        except AttributeError as exc:
            raise TypeError(f"{name}.Meta.db_type is required.") from exc

        meta_obj.fields = fields

        # create the field for this Type
        attrs["Field"] = type(f"{name}Field", (BaseField,), {"Meta": meta_obj})

        # add field class to the module in which the composite type class lives
        # this is required for migrations to work
        _add_class_to_module(attrs["Field"], attrs["__module__"])

        # create the database operation for this type
        attrs["Operation"] = type(
            f"Create{name}Type", (BaseOperation,), {"Meta": meta_obj}
        )

        # create the caster for this type
        attrs["Caster"] = type(f"{name}Caster", (BaseCaster,), {"Meta": meta_obj})

        new_cls = super().__new__(cls, name, bases, attrs)
        new_cls._meta = meta_obj

        meta_obj.model = new_cls

        return new_cls

    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        if name == "CompositeType":
            return

        cls._capture_descriptors()  # pylint:disable=no-value-for-parameter

        # Register the type on the first database connection
        connection_created.connect(
            receiver=cls.database_connected, dispatch_uid=cls._meta.db_type
        )

    def _capture_descriptors(cls):
        """Work around for not being able to call contribute_to_class.

        Too much code to fake in our meta objects etc to be able to call
        contribute_to_class directly, but we still want fields to be able
        to set custom type descriptors. So we fake a model instead, with the
        same fields as the composite type, and extract any custom descriptors
        on that.
        """

        attrs = dict(cls._meta.fields)

        # we need to build a unique app label and model name combination for
        # every composite type so django doesn't complain about model reloads
        class Meta:
            app_label = cls.__module__

        attrs["__module__"] = cls.__module__
        attrs["Meta"] = Meta
        model_name = f"_Fake{cls.__name__}Model"

        fake_model = type(model_name, (models.Model,), attrs)
        for field_name, _ in cls._meta.fields:
            attr = getattr(fake_model, field_name)
            if inspect.isdatadescriptor(attr):
                setattr(cls, field_name, attr)

    def database_connected(cls, signal, sender, connection, **kwargs):
        """
        Register this type with the database the first time a connection is
        made.
        """
        if isinstance(connection, PostgresDatabaseWrapper):
            # Try to register the type. If the type has not been created in a
            # migration, the registration will fail. The type will be
            # registered as part of the migration, so hopefully the migration
            # will run soon.
            try:
                cls.register_composite(connection)
            except ProgrammingError:
                LOGGER.warning(
                    "Failed to register composite %s. "
                    "The migration to register it may not have run yet.",
                    cls.__name__,
                )

        # Disconnect the signal now - only need to register types on the
        # initial connection
        connection_created.disconnect(
            cls.database_connected, dispatch_uid=cls._meta.db_type
        )


class CompositeType(metaclass=CompositeTypeMeta):
    """
    A new composite type stored in Postgres.
    """

    _meta = None

    # The database connection this type is registered with
    registered_connection = None

    def __init__(self, *args, **kwargs):
        if args and kwargs:
            raise RuntimeError("Specify either args or kwargs but not both.")

        # Initialise blank values for anyone expecting them
        for name, _ in self._meta.fields:
            setattr(self, name, None)

        # Unpack any args as if they came from the type
        for (name, _), arg in zip(self._meta.fields, args):
            setattr(self, name, arg)

        for name, value in kwargs.items():
            setattr(self, name, value)

    def __repr__(self):
        args = ", ".join(f"{k}={v}" for k, v in self.__to_dict__().items())
        return f"<{type(self).__name__}({args})>"

    def __to_tuple__(self):
        return tuple(
            field.get_prep_value(getattr(self, name))
            for name, field in self._meta.fields
        )

    def __to_dict__(self):
        return {
            name: field.get_prep_value(getattr(self, name))
            for name, field in self._meta.fields
        }

    def __eq__(self, other):
        if not isinstance(other, CompositeType):
            return False
        if self._meta.model != other._meta.model:
            return False
        for name, _ in self._meta.fields:
            if getattr(self, name) != getattr(other, name):
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
                cls._meta.db_type, cur, globally=True, factory=cls.Caster
            )
            # This is what to do when the type is going in to the database
            register_adapter(cls, QuotedCompositeType)

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

    class Operation(BaseOperation):
        """
        Placeholder for the DB operation that will be produced for this type.
        """

    class Caster(CompositeCaster):
        """
        Placeholder for the caster that will be produced for this type
        """
