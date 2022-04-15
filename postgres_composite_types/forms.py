"""
Form fields for composite types

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

Takes inspiration from django.forms.MultiValueField/MultiWidget.
"""

import copy
import logging
import json
from collections import OrderedDict

from django import VERSION, forms
from django.db import models
from django.forms.widgets import TextInput

from django.contrib.postgres.utils import prefix_validation_error
from django.core.exceptions import ImproperlyConfigured
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.forms import SimpleArrayField
from django.utils.translation import ugettext as _

from django_jsonform.widgets import JSONFormWidget

from . import CompositeType

LOGGER = logging.getLogger(__name__)

DJANGO21 = VERSION >= (2, 1)


class CompositeBoundField(forms.BoundField):
    """
    Allow access to nested BoundFields for fields. Useful for customising the
    rendering of a CompositeTypeField:

        <label for="{{ form.address.id_for_widget }}">Address:</label>
        {{ form.address.address_1 }}
        {{ form.address.address_2 }}
        <label for="{{ form.address.suburb }}">Suburb:</label>
        {{ form.address.suburb }}
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bound_fields_cache = {}

        initial = self.form.initial.get(self.name, self.field.initial)
        if isinstance(initial, CompositeType):
            initial = initial.__to_dict__()

        if self.form.is_bound:
            data = self.form.data
        else:
            data = None

        self.composite_form = forms.Form(
            data=data, initial=initial, prefix=self.form.add_prefix(self.name))
        self.composite_form.fields = copy.deepcopy(self.field.fields)

    def __getitem__(self, name):
        "Returns a BoundField with the given name."
        return self.composite_form[name]


class CompositeTypeField(forms.Field):
    """
    Takes an ordered dict of fields to produce a composite form field
    """

    default_error_messags = {
        'field_invalid': _('%s: '),
    }

    def __init__(self, *args, fields=None, model=None, **kwargs):
        if fields is None:
            fields = OrderedDict([
                (name, field.formfield())
                for name, field in model._meta.fields
            ])
        else:
            fields = OrderedDict(fields)

        widget = CompositeTypeWidget(widgets=[
            (name, field.widget)
            for name, field in fields.items()
        ])

        super().__init__(*args, widget=widget, **kwargs)
        self.fields = fields
        self.model = model

        for field, widget in zip(fields.values(),
                                 self.widget.widgets.values()):
            widget.attrs['placeholder'] = field.label

    def get_schema(self):
        schema = {'type': 'object', 'properties': {}}
        for name, field in self.fields.items():
            if isinstance(field, CompositeTypeField):
                field_schema = field.get_schema()
            elif isinstance(field, models.IntegerField):
                field_schema = {'type': 'number'}
            else:
                field_schema = {'type': 'string'}
            schema['properties'][name] = field_schema
        return schema

    def prepare_value(self, value):
        """
        Prepare the field data for the CompositeTypeWidget, which expects data
        as a dict.
        """
        if isinstance(value, CompositeType):
            return value.__to_dict__()

        if value is None:
            return {}

        return value

    def validate(self, value):
        pass

    def clean(self, value):
        LOGGER.debug("clean: > %s", value)

        if all(value.get(name) in field.empty_values
               for name, field in self.fields.items()):
            if self.required:
                raise forms.ValidationError("This section is required",
                                            code='incomplete')
            else:
                value = None

        else:
            cleaned_data = {}
            errors = []

            for name, field in self.fields.items():
                try:
                    cleaned_data[name] = field.clean(value.get(name))
                except forms.ValidationError as error:
                    if DJANGO21:
                        prefix = '%(label)s:'
                    else:
                        prefix = '%(label)s: '
                    errors.append(prefix_validation_error(
                        error, code='field_invalid',
                        prefix=prefix, params={'label': field.label}))
            if errors:
                raise forms.ValidationError(errors)
            value = self.model(**cleaned_data)

        LOGGER.debug("clean: < %s", value)

        return value

    def has_changed(self, initial, data):
        return initial != data

    def get_bound_field(self, form, field_name):
        """
        Return a CompositeBoundField instance that will be used when accessing
        the fields in a template.
        """
        return CompositeBoundField(form, self, field_name)


class CompositeTypeWidget(forms.Widget):
    """
    Takes an ordered dict of widgets to produce a composite form widget. This
    widget knows nothing about CompositeTypes, and works only with dicts for
    initial and output data.
    """
    template_name = \
        'postgres_composite_types/forms/widgets/composite_type.html'

    def __init__(self, widgets, **kwargs):
        self.widgets = OrderedDict(
            (name, widget() if isinstance(widget, type) else widget)
            for name, widget in OrderedDict(widgets).items()
        )

        super().__init__(**kwargs)

    @property
    def is_hidden(self):
        return all(w.is_hidden for w in self.widgets.values())

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        final_attrs = context['widget']['attrs']
        id_ = context['widget']['attrs'].get('id')

        if self.is_localized:
            for widget in self.widgets.values():
                widget.is_localized = self.is_localized

        subwidgets = {}
        for subname, widget in self.widgets.items():
            widget_attrs = final_attrs.copy()
            if id_:
                widget_attrs['id'] = '%s-%s' % (id_, subname)

            widget_context = widget.get_context(
                '%s-%s' % (name, subname),
                value.get(subname),
                widget_attrs)
            subwidgets[subname] = widget_context['widget']

        context['widget']['subwidgets'] = subwidgets
        return context

    def value_from_datadict(self, data, files, name):
        return {
            subname: widget.value_from_datadict(data, files,
                                                '%s-%s' % (name, subname))
            for subname, widget in self.widgets.items()
        }

    def value_omitted_from_data(self, data, files, name):
        prefix = '{}-'.format(name)
        return not any(key.startswith(prefix) for key in data)

    def id_for_label(self, id_):
        """
        Wrapper around the field widget's `id_for_label` method.
        Useful, for example, for focusing on this field regardless of whether
        it has a single widget or a MultiWidget.
        """
        if id_:
            name = next(iter(self.widgets.keys()))
            return '%s-%s' % (id_, name)

        return id_


class CompositesArrayField(ArrayField):
    def __init__(self, *args, **kwargs):
        if hasattr(ArrayField, 'mock_field'):
            raise ImproperlyConfigured('ArrayField requires psycopg2 to be installed.')

        self.nested = kwargs.pop('nested', False)
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        return super().formfield(**{'form_class': CompositesArrayFormField, 'nested': self.nested, **kwargs})

class CompositesArrayFormField(SimpleArrayField):
    def __init__(self, base_field, **kwargs):
        self.base_field = base_field
        self.max_items = kwargs.get('max_length', kwargs.get('size', None))
        self.min_items = kwargs.get('min_length')

        self.nested = kwargs.pop('nested', False)
        if not self.nested:
            self.widget = JSONFormWidget(schema=self.get_schema())
        else:
            self.widget = TextInput
        kwargs['widget'] = self.widget

        super().__init__(base_field, **kwargs)


    def composite_prep(self, value):
        """
        Prepare the field data for the CompositeTypeWidget, which expects data
        as a dict.
        """
        if isinstance(value, CompositeType):
            prepped_fields = []
            for name, field in value._meta.fields:
                if isinstance(getattr(value, name), CompositeType):
                    prepped_fields.append((name, self.composite_prep(getattr(value, name))))
                else:
                    prepped_fields.append((name, field.get_prep_value(getattr(value, name))))
            return OrderedDict(prepped_fields)

        if value is None:
            return {}

        return value

    def prepare_value(self, value):
        if isinstance(value, list):
            value = [(self.composite_prep(k) if isinstance(k, CompositeType) else json.dumps(k)) for k in value]
        return json.dumps(value)

    def to_python(self, value):
        value = json.loads(value)
        return super().to_python(value)

    def get_schema(self):
        schema = {'type': 'array'}
        if isinstance(self.base_field, CompositesArrayFormField):
            items = self.base_field.get_schema()
        elif isinstance(self.base_field, CompositeTypeField):
            items = self.base_field.get_schema()
        elif  isinstance(self.base_field, models.IntegerField):
            items = {'type': 'number'}
        else:
            items = {'type': 'string'}

        schema['items'] = items

        if self.max_items:
            schema['max_items'] = self.max_items
        if self.min_items:
            schema['min_items'] = self.min_items
        return schema
