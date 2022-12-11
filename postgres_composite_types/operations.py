from django.db.migrations.operations.base import Operation

from .signals import composite_type_created

__all__ = ["BaseOperation"]


def sql_field_definition(field_name, field, schema_editor):
    quoted_name = schema_editor.quote_name(field_name)
    type_name = field.db_type(schema_editor.connection)
    return f"{quoted_name} {type_name}"


def sql_create_type(type_name, fields, schema_editor):
    fields_list = ", ".join(
        sql_field_definition(field_name, field, schema_editor)
        for field_name, field in fields
    )
    quoted_name = schema_editor.quote_name(type_name)
    return f"CREATE TYPE {quoted_name} AS ({fields_list})"


def sql_drop_type(type_name, schema_editor):
    quoted_name = schema_editor.quote_name(type_name)
    return f"DROP TYPE {quoted_name}"


class BaseOperation(Operation):
    """Base class for the DB operation that relates to this type."""

    reversible = True
    Meta = None

    def state_forwards(self, app_label, state):
        pass

    def describe(self):
        return f"Creates type {self.Meta.db_table}"

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        schema_editor.execute(
            sql_create_type(self.Meta.db_table, self.Meta.fields, schema_editor)
        )
        self.Meta.model.register_composite(schema_editor.connection)
        composite_type_created.send(
            self.Meta.model, connection=schema_editor.connection
        )

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        schema_editor.execute(
            sql_drop_type(self.Meta.db_table, schema_editor=schema_editor)
        )
