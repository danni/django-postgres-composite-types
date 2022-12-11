"""
Form fields for composite types

Takes inspiration from django.forms.MultiValueField/MultiWidget.
"""

import copy
import logging

from django import forms
from django.contrib.postgres.utils import prefix_validation_error
from django.utils.translation import gettext as _

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
            data=data, initial=initial, prefix=self.form.add_prefix(self.name)
        )
        self.composite_form.fields = copy.deepcopy(self.field.fields)

    def __getitem__(self, name):
        "Returns a BoundField with the given name."
        return self.composite_form[name]


class CompositeTypeField(forms.Field):
    """
    Takes an ordered dict of fields to produce a composite form field
    """

    default_error_messags = {
        "field_invalid": _("%s: "),
    }

    def __init__(self, *args, fields=None, model=None, **kwargs):
        fields = {
            field.name: field.formfield() for field in fields or model._meta.fields
        }

        widget = CompositeTypeWidget(
            widgets=[
                (name, getattr(field, "widget", None)) for name, field in fields.items()
            ]
        )

        super().__init__(*args, widget=widget, **kwargs)
        self.fields = fields
        self.model = model

        for field, widget in zip(fields.values(), self.widget.widgets.values()):
            if widget:
                widget.attrs["placeholder"] = getattr(field, "label", "")

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

        if all(
            value.get(name) in field.empty_values for name, field in self.fields.items()
        ):
            value = None
            if self.required:
                raise forms.ValidationError(
                    "This section is required", code="incomplete"
                )

        else:
            cleaned_data = {}
            errors = []

            for name, field in self.fields.items():
                try:
                    cleaned_data[name] = field.clean(value.get(name))
                except forms.ValidationError as error:
                    prefix = "%(label)s:"
                    errors.append(
                        prefix_validation_error(
                            error,
                            code="field_invalid",
                            prefix=prefix,
                            params={"label": field.label},
                        )
                    )
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

    template_name = "postgres_composite_types/forms/widgets/composite_type.html"

    def __init__(self, widgets, **kwargs):
        self.widgets = {
            name: widget() if isinstance(widget, type) else widget
            for name, widget in dict(widgets).items()
        }

        super().__init__(**kwargs)

    @property
    def is_hidden(self):
        return all(w.is_hidden for w in self.widgets.values())

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        final_attrs = context["widget"]["attrs"]
        id_ = context["widget"]["attrs"].get("id")

        if self.is_localized:
            for widget in self.widgets.values():
                widget.is_localized = self.is_localized

        subwidgets = {}
        for subname, widget in self.widgets.items():
            widget_attrs = final_attrs.copy()
            if id_:
                widget_attrs["id"] = f"{id_}-{subname}"

            widget_context = widget.get_context(
                f"{name}-{subname}", value.get(subname), widget_attrs
            )
            subwidgets[subname] = widget_context["widget"]

        context["widget"]["subwidgets"] = subwidgets
        return context

    def value_from_datadict(self, data, files, name):
        return {
            subname: widget.value_from_datadict(data, files, f"{name}-{subname}")
            for subname, widget in self.widgets.items()
        }

    def value_omitted_from_data(self, data, files, name):
        prefix = f"{name}-"
        return not any(key.startswith(prefix) for key in data)

    def id_for_label(self, id_):
        """
        Wrapper around the field widget's `id_for_label` method.
        Useful, for example, for focusing on this field regardless of whether
        it has a single widget or a MultiWidget.
        """
        if id_:
            name = next(iter(self.widgets.keys()))
            return f"{id_}-{name}"

        return id_
