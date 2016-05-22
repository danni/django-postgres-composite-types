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

import logging
from collections import OrderedDict

from django import forms
from django.utils.safestring import mark_safe

LOGGER = logging.getLogger(__name__)


class CompositeTypeField(forms.Field):
    """
    Takes an ordered dict of fields to produce a composite form field
    """

    def __init__(self, *args, fields=None, model=None, **kwargs):
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

    def validate(self, value):
        pass

    def clean(self, value):
        LOGGER.debug("clean: > %s", value)

        if all(elem is None or elem == '' for elem in value.values()):
            if self.required:
                raise forms.ValidationError("This section is required",
                                            code='incomplete')
            else:
                value = None

        else:
            value = self.model(**{
                name: field.clean(value.get(name))
                for name, field in self.fields.items()
            })

        LOGGER.debug("clean: < %s", value)

        return value

    def has_changed(self, initial, data):
        return initial != data


class CompositeTypeWidget(forms.Widget):
    """
    Takes an ordered dict of widgets to produce a composite form widget
    """
    def __init__(self, widgets, **kwargs):
        self.widgets = OrderedDict(
            (name, widget() if isinstance(widget, type) else widget)
            for name, widget in OrderedDict(widgets).items()
        )

        super().__init__(**kwargs)

    @property
    def is_hidden(self):
        return all(w.is_hidden for w in self.widgets)

    def render(self, name, value, attrs=None):
        if self.is_localized:
            for widget in self.widgets.values():
                widget.is_localized = self.is_localized

        output = []
        final_attrs = self.build_attrs(attrs)
        id_ = final_attrs.get('id')

        for subname, widget in self.widgets.items():
            if id_:
                final_attrs = dict(final_attrs, id='%s_%s' % (id_, subname))

            output.append(widget.render('%s_%s' % (name, subname),
                                        getattr(value, subname, None),
                                        final_attrs))

        return mark_safe(''.join(output))

    def value_from_datadict(self, data, files, name):
        return {
            subname: widget.value_from_datadict(data, files,
                                                '%s_%s' % (name, subname))
            for subname, widget in self.widgets.items()
        }
