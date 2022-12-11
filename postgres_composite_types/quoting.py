from psycopg2.errors import ProgrammingError
from psycopg2.extensions import ISQLQuote, adapt

__all__ = ["QuotedCompositeType"]


class QuotedCompositeType:
    """
    A wrapper for CompositeTypes that knows how to convert itself into a safe
    postgres representation. Created from CompositeType.__conform__
    """

    value = None
    prepared = False

    def __init__(self, obj):
        self.obj = obj
        self.model = obj._meta.model

        self.value = adapt(
            tuple(
                field.get_db_prep_value(
                    field.value_from_object(self.obj),
                    self.model.registered_connection,
                )
                for field in self.model._meta.fields
            )
        )

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
            name = type(self).__name__
            raise RuntimeError(
                f"{name}.prepare() must be called before {name}.getquoted()"
            )

        db_type = self.model._meta.db_table.encode("ascii")
        return self.value.getquoted() + b"::" + db_type
