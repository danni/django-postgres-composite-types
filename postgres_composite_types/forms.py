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
from collections import OrderedDict

from django import forms
from django.contrib.postgres.utils import prefix_validation_error
from django.utils.translation import ugettext as _

from . import CompositeType

LOGGER = logging.getLogger(__name__)


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

    def prepare_value(self, value):
        """
        Prepare the field data for the CompositeTypeWidget, which expects data
        as a dict.
        """
        if isinstance(value, CompositeType):
            return value.__to_dict__()

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
                    errors.append(prefix_validation_error(
                        error, code='field_invalid',
                        prefix='%(label)s: ', params={'label': field.label}))
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
