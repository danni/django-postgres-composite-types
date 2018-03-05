"""
Implementation of Postgres composite types in Django.

(c) 2016, Danielle Madeley  <danielle@madeley.id.au>
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

Takes inspiration from:
 - django-pgfields
 - django-postgres
"""

import inspect
import json
import logging
import sys
from collections import OrderedDict

from django.core.exceptions import ValidationError
from django.db import migrations, models
from django.db.backends.postgresql.base import \
    DatabaseWrapper as PostgresDatabaseWrapper
from django.db.backends.signals import connection_created
from django.dispatch import Signal
from psycopg2 import ProgrammingError
from psycopg2.extensions import ISQLQuote, adapt, register_adapter
from psycopg2.extras import CompositeCaster, register_composite

LOGGER = logging.getLogger(__name__)

__all__ = ['CompositeType']


class QuotedCompositeType(object):
    """
    A wrapper for CompositeTypes that knows how to convert itself into a safe
    postgres representation. Created from CompositeType.__conform__
    """
    value = None
    prepared = False

    def __init__(self, obj):
        self.obj = obj
        self.model = obj._meta.model

        self.value = adapt(tuple(
            field.get_db_prep_value(field.value_from_object(self.obj),
                                    self.model.registered_connection)
            for _, field in self.model._meta.fields))

    def __conform__(self, protocol):
        """
        QuotedCompositeType conform to the ISQLQuote protocol all by
        themselves. This is required for nested composite types.

        Returns None if it can not conform to the requested protocol.
        """
        if protocol is ISQLQuote:
            return self

        return None

    def prepare(self, connection):
        """
        Prepare anything that depends on the database connection, such as
        strings with encodings.
        """
        self.value.prepare(connection)
        self.prepared = True

    def getquoted(self):
        """
        Format composite types as the correct Postgres snippet, including
        casts, for queries.

        Returns something like ``b"(value1, value2)::type_name"``
        """
        if not self.prepared:
            raise RuntimeError("{name}.prepare() must be called before "
                               "{name}.getquoted()".format(
                                   name=type(self).__name__))

        db_type = self.model._meta.db_type.encode('ascii')
        return self.value.getquoted() + b'::' + db_type


class BaseField(models.Field):
    """Base class for the field that relates to this type."""

    Meta = None

    default_error_messages = {
        'bad_json': "to_python() received a string that was not valid JSON",
    }

    def db_type(self, connection):
        LOGGER.debug("db_type")

        if not isinstance(connection, PostgresDatabaseWrapper):
            raise RuntimeError("Composite types are only available "
                               "for postgres")

        return self.Meta.db_type

    def formfield(self, **kwargs):  # pylint:disable=arguments-differ
        """Form field for address."""
        from .forms import CompositeTypeField

        defaults = {
            'form_class': CompositeTypeField,
            'model': self.Meta.model,
        }
        defaults.update(kwargs)

        return super().formfield(**defaults)

    def to_python(self, value):
        """
        Convert a value to the correct type for this field. Values from the
        database will already be of the correct type, due to the the caster
        registered with psycopg2. The field can also be serialized as a string
        via value_to_string, where it is encoded as a JSON object.
        """
        # Composite types are serialized as JSON blobs. If BaseField.to_python
        # is called with a string, assume it was produced by value_to_string
        # and decode it
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                raise ValidationError(
                    self.error_messages['bad_json'],
                    code='bad_json',
                )
            return self.Meta.model(**{
                name: field.to_python(value.get(name))
                for name, field in self.Meta.fields
            })

        return super().to_python(value)

    def value_to_string(self, obj):
        """
        Serialize this as a JSON object {name: field.value_to_string(...)} for
        each child field.
        """
        value = self.value_from_object(obj)
        return json.dumps({
            name: field.value_to_string(value)
            for name, field in self.Meta.fields
        })


class BaseOperation(migrations.operations.base.Operation):
    """Base class for the DB operation that relates to this type."""

    reversible = True
    Meta = None

    def state_forwards(self, app_label, state):
        pass

    def describe(self):
        return 'Creates type %s' % self.Meta.db_type

    def database_forwards(self, app_label, schema_editor,
                          from_state, to_state):

        fields = [
            '%s %s' % (schema_editor.quote_name(name),
                       field.db_type(schema_editor.connection))
            for name, field in self.Meta.fields
        ]

        schema_editor.execute(' '.join((
            "CREATE TYPE",
            schema_editor.quote_name(self.Meta.db_type),
            "AS (%s)" % ', '.join(fields),
        )))

        self.Meta.model.register_composite(schema_editor.connection)

        composite_type_created.send(self.Meta.model,
                                    connection=schema_editor.connection)

    def database_backwards(self, app_label, schema_editor,
                           from_state, to_state):
        type_name = schema_editor.quote_name(self.Meta.db_type)
        schema_editor.execute('DROP TYPE %s' % type_name)


class BaseCaster(CompositeCaster):
    """
    Base caster to transform a tuple of values from postgres to a model
    instance.
    """
    Meta = None

    def make(self, values):
        return self.Meta.model(*values)


def _add_class_to_module(cls, module_name):
    cls.__module__ = module_name
    module = sys.modules[module_name]
    setattr(module, cls.__name__, cls)


class CompositeTypeMeta(type):
    """Metaclass for Type."""

    @classmethod
    def __prepare__(mcs, name, bases):
        """
        Guarantee the ordering of the declared attrs.

        We need this so that our type doesn't change ordering between
        invocations.
        """
        return OrderedDict()

    def __new__(mcs, name, bases, attrs):
        # Only apply the metaclass to our subclasses
        if name == 'CompositeType':
            return super().__new__(mcs, name, bases, attrs)

        # retrieve any fields from our declaration
        fields = []
        for field_name, value in attrs.copy().items():
            if isinstance(value, models.fields.related.RelatedField):
                raise TypeError("Composite types cannot contain "
                                "related fields")
            elif isinstance(value, models.Field):
                field = attrs.pop(field_name)
                field.set_attributes_from_name(field_name)
                fields.append((field_name, field))

        # retrieve the Meta from our declaration
        try:
            meta_obj = attrs.pop('Meta')
        except KeyError:
            raise TypeError('%s has no "Meta" class' % (name,))

        try:
            meta_obj.db_type
        except AttributeError:
            raise TypeError("%s.Meta.db_type is required." % (name,))

        meta_obj.fields = fields

        # create the field for this Type
        attrs['Field'] = type('%sField' % name,
                              (BaseField,),
                              {'Meta': meta_obj})

        # add field class to the module in which the composite type class lives
        # this is required for migrations to work
        _add_class_to_module(attrs['Field'], attrs['__module__'])

        # create the database operation for this type
        attrs['Operation'] = type('Create%sType' % name,
                                  (BaseOperation,),
                                  {'Meta': meta_obj})

        # create the caster for this type
        attrs['Caster'] = type('%sCaster' % name,
                               (BaseCaster,),
                               {'Meta': meta_obj})

        new_cls = super().__new__(mcs, name, bases, attrs)
        new_cls._meta = meta_obj

        meta_obj.model = new_cls

        return new_cls

    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        if name == 'CompositeType':
            return

        cls._capture_descriptors()  # pylint:disable=no-value-for-parameter

        # Register the type on the first database connection
        connection_created.connect(receiver=cls.database_connected,
                                   dispatch_uid=cls._meta.db_type)

    def _capture_descriptors(cls):
        """Work around for not being able to call contribute_to_class.

        Too much code to fake in our meta objects etc to be able to call
        contribute_to_class directly, but we still want fields to be able
        to set custom type descriptors. So we fake a model instead, with the
        same fields as the composite type, and extract any custom descriptors
        on that.
        """

        attrs = {field_name: field for field_name, field in cls._meta.fields}

        # we need to build a unique app label and model name combination for
        # every composite type so django doesn't complain about model reloads
        class Meta:
            app_label = cls.__module__
        attrs['__module__'] = cls.__module__
        attrs['Meta'] = Meta
        model_name = '_Fake{}Model'.format(cls.__name__)

        fake_model = type(model_name, (models.Model,), attrs)
        for field_name, _ in cls._meta.fields:
            # default None is for django 1.9
            attr = getattr(fake_model, field_name, None)
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
                    "Failed to register composite %s. This might be because "
                    "the migration to register it has not run yet",
                    cls.__name__)

        # Disconnect the signal now - only need to register types on the
        # initial connection
        connection_created.disconnect(cls.database_connected,
                                      dispatch_uid=cls._meta.db_type)


# pylint:disable=invalid-name
composite_type_created = Signal()
# pylint:enable=invalid-name


class CompositeType(object, metaclass=CompositeTypeMeta):
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
        return '<%s(%s)>' % (
            type(self).__name__,
            ', '.join('%s=%s' % item for item in self.__to_dict__().items()),
        )

    def __to_tuple__(self):
        return tuple(
            field.get_prep_value(getattr(self, name))
            for name, field in self._meta.fields
        )

    def __to_dict__(self):
        return OrderedDict(
            (name, field.get_prep_value(getattr(self, name)))
            for name, field in self._meta.fields
        )

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

        LOGGER.debug("Registering composite type %s on connection %s",
                     cls.__name__, connection)
        cls.registered_connection = connection

        with connection.temporary_connection() as cur:
            # This is what to do when the type is coming out of the database
            register_composite(cls._meta.db_type, cur, globally=True,
                               factory=cls.Caster)
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
