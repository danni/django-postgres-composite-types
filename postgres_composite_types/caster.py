from psycopg2.extras import CompositeCaster

__all__ = ["BaseCaster"]


class BaseCaster(CompositeCaster):
    """
    Base caster to transform a tuple of values from postgres to a model
    instance.
    """

    def make(self, values):
        return self._composite_type_model(*values)
