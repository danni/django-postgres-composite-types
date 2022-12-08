from django.db.migrations.operations.base import Operation

from .signals import composite_type_created

__all__ = ["BaseOperation"]


class BaseOperation(Operation):
    """Base class for the DB operation that relates to this type."""

    reversible = True
    Meta = None

    def state_forwards(self, app_label, state):
        pass

    def describe(self):
        return f"Creates type {self.Meta.db_type}"

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        connection = schema_editor.connection
        fields = ", ".join(
            f"{schema_editor.quote_name(name)} {field.db_type(connection)}"
            for name, field in self.Meta.fields
        )

        type_name = schema_editor.quote_name(self.Meta.db_type)

        schema_editor.execute(f"CREATE TYPE {type_name} AS ({fields})")

        self.Meta.model.register_composite(connection)

        composite_type_created.send(self.Meta.model, connection=connection)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        type_name = schema_editor.quote_name(self.Meta.db_type)
        schema_editor.execute(f"DROP TYPE {type_name}")
