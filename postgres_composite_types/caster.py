from typing import TYPE_CHECKING, Type

from psycopg2.extras import CompositeCaster

if TYPE_CHECKING:
    from .composite_type import CompositeType

__all__ = ["BaseCaster"]


class BaseCaster(CompositeCaster):
    """
    Base caster to transform a tuple of values from postgres to a model
    instance.
    """

    _composite_type_model: Type["CompositeType"]

    def make(self, values):
        return self._composite_type_model(*values)
