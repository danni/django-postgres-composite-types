from django.db.migrations import CreateModel
from django.db.migrations.state import ModelState

from .fields import DummyField

__all__ = ["CreateType"]


def sql_field_definition(field_name, field, schema_editor):
    quoted_name = schema_editor.quote_name(field_name)
    type_name = field.db_type(schema_editor.connection)
    return f"{quoted_name} {type_name}"


def sql_create_type(type_name, fields, schema_editor):
    fields_list = ", ".join(
        sql_field_definition(field_name, field, schema_editor)
        for field_name, field in fields
        if field_name != "__id"
    )
    quoted_name = schema_editor.quote_name(type_name)
    return f"CREATE TYPE {quoted_name} AS ({fields_list})"


def sql_drop_type(type_name, schema_editor):
    quoted_name = schema_editor.quote_name(type_name)
    return f"DROP TYPE {quoted_name}"


class CreateType(CreateModel):
    """Base class for the DB operation that relates to this type."""

    reversible = True

    def __init__(self, *, name: str, fields, options) -> None:
        fields = [("__id", DummyField(primary_key=True, serialize=False)), *fields]
        super().__init__(name, fields, options)

    def describe(self):
        return f"Creates type {self.name}"

    def state_forwards(self, app_label, state) -> None:
        state.add_model(
            ModelState(app_label, self.name, list(self.fields), dict(self.options))
        )

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        schema_editor.execute(
            sql_create_type(self.options["db_table"], self.fields, schema_editor)
        )

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        schema_editor.execute(
            sql_drop_type(self.options["db_table"], schema_editor=schema_editor)
        )
