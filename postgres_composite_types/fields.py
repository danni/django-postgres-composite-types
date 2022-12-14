import json

from django.core.exceptions import ValidationError
from django.db.backends.postgresql.base import (
    DatabaseWrapper as PostgresDatabaseWrapper,
)
from django.db.models import Field

__all__ = ["BaseField"]


class DummyField(Field):
    """
    A dummy field added on every CompositeType, that behaves as the
    type's primary key. This is a hack due to Django's requirement for
    all models to have a primary key.
    """


class BaseField(Field):
    """Base class for the field that relates to this type."""

    default_error_messages = {
        "bad_json": "to_python() received a string that was not valid JSON",
    }

    def db_type(self, connection):
        if not isinstance(connection, PostgresDatabaseWrapper):
            raise RuntimeError("Composite types are only available for postgres")

        return self._composite_type_model._meta.db_table

    def formfield(self, **kwargs):  # pylint:disable=arguments-differ
        """Form field for address."""
        from .forms import CompositeTypeField

        defaults = {
            "form_class": CompositeTypeField,
            "model": self._composite_type_model,
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
            except ValueError as exc:
                raise ValidationError(
                    self.error_messages["bad_json"],
                    code="bad_json",
                ) from exc

            return self._composite_type_model(
                **{
                    field.name: field.to_python(value.get(field.name))
                    for field in self._composite_type_model._meta.fields
                    if field.name != "pk"
                }
            )

        return super().to_python(value)

    def value_to_string(self, obj):
        """
        Serialize this as a JSON object {name: field.value_to_string(...)} for
        each child field.
        """
        value = self.value_from_object(obj)
        return json.dumps(
            {
                field.name: field.value_to_string(value)
                for field in self._composite_type_model._meta.fields
                if field.name != "pk"
            }
        )
