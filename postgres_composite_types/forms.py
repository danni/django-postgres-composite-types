"""
Form fields for composite types
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

        if all(elem is None for elem in value.values()):
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
                                        getattr(value, subname),
                                        final_attrs))

        return mark_safe(''.join(output))

    def value_from_datadict(self, data, files, name):
        return {
            subname: widget.value_from_datadict(data, files,
                                                '%s_%s' % (name, subname))
            for subname, widget in self.widgets.items()
        }
