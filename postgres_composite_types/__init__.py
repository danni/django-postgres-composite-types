"""
Implementation of Postgres composite types in Django.

Takes inspiration from:
 - django-pgfields
 - django-postgres
"""

from .composite_type import CompositeType

__all__ = ["CompositeType"]
