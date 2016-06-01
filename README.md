Django Postgres composite types
===============================

An implementation of Postgres' [composite types](http://www.postgresql.org/docs/current/static/rowtypes.html)
for [Django](https://docs.djangoproject.com/en/1.9/).

Usage
-----

Install with:

    pip install django-postgres-composite-types

Define a type and add it to a model:

```python
from django.db import models
from postgres_composite_type import CompositeType

class Address(CompositeType):
    """An address."""

    address_1 = models.CharField(max_length=255)
    address_2 = models.CharField(max_length=255)

    suburb = models.CharField(max_length=50)
    state = models.CharField(max_length=50)

    postcode = models.CharField(max_length=10)
    country = models.CharField(max_length=50)

    class Meta:
        db_type = 'x_address'  # Required


class Person(models.Model):
    """A person."""

    address = Address.Field()
```

An operation needs to be prepended to your migration:

```python
import address
from django.db import migrations


class Migration(migrations.Migration):

    operations = [
        # Registers the type
        address.Address.Operation(),
        migrations.AddField(
            model_name='person',
            name='address',
            field=address.Address.Field(blank=True, null=True),
        ),
    ]
```

Examples
--------

Array fields:

```python
class Card(CompositeType):
    """A playing card."""

    suit = models.CharField(max_length=1)
    rank = models.CharField(max_length=2)

    class Meta:
        db_type = 'card'


class Hand(models.Model):
    """A hand of cards."""
    cards = ArrayField(base_field=Card.Field())
```

Nested types:

```python
class Point(CompositeType):
    """A point on the cartesian plane."""

    # pylint:disable=invalid-name
    x = models.IntegerField()
    y = models.IntegerField()

    class Meta:
        db_type = 'x_point'  # Postgres already has a point type


class Box(CompositeType):
    """An axis-aligned box on the cartesian plane."""
    class Meta:
        db_type = 'x_box'  # Postgres already has a box type

    top_left = Point.Field()
    bottom_right = Point.Field()
```

Gotchas and Caveats
-------------------

The migration operation currently loads the *current* state of the type, not
the state when the migration was written. A generic `CreateType` operation
which takes the fields of the type would be possible, but it would still
require manual handling still as Django's `makemigrations` is not currently
extensible.

Changes to types are possible using `RawSQL`, for example:

```python
operations = [
    migrations.RunSQL([
        "ALTER TYPE x_address DROP ATTRIBUTE country",
        "ALTER TYPE x_address ADD ATTRIBUTE country integer",
    ], [
        "ALTER TYPE x_address DROP ATTRIBUTE country",
        "ALTER TYPE x_address ADD ATTRIBUTE country varchar(50)",
    ]),
]
```

However, be aware that if your earlier operations were run using current DB
code, you will already have the right types
([bug #8](https://github.com/danni/django-postgres-composite-types/issues/8)).

It is recommended to that you namespace your custom types to avoid conflict
with future PostgreSQL types.

Lookups and indexes are not implemented yet
([bug #9](https://github.com/danni/django-postgres-composite-types/issues/9),
[bug #10](https://github.com/danni/django-postgres-composite-types/issues/10)).

Authors
-------

* Danielle Madeley <danielle@madeley.id.au>
* Tim Heap <hello@timheap.me>

License
-------

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
