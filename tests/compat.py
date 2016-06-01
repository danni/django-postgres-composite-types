"""
Compatibility shims for running tests over multiple Django versions
"""
import django

# Importing things in the 'wrong' version of Django makes pylint complain
# pylint:disable=no-name-in-module,import-error
# Importing things in an if: makes pylint complain
# pylint:disable=wrong-import-position

__all__ = ['ArrayField']

if django.VERSION >= (1, 10):  # pylint:disable=too-complex
    from django.contrib.postgres.fields.array import ArrayField
else:
    from django.core.exceptions import ValidationError
    from django.contrib.postgres.fields.array import \
        ArrayField as BaseArrayField

    from postgres_composite_types.compat import prefix_validation_error

    class ArrayField(BaseArrayField):
        """
        Django ArrayField has a bug with validation errors from the child
        field.  A new ValidationError is constructed with the error from the
        child, but the params dict is not included. If the child
        ValidationError message contains format placeholders, the new
        ValidationError throws an error when ever something tries to call `str`
        or `repr` on it - which includes the templates when rendering errors
        (which throws an error), and Djangos fancy debug error page. Fun times.

        Similar to https://code.djangoproject.com/ticket/25841 but for the
        ArrayField itself.

        The buggy methods have been overridden below to fix the ValidationError
        construction.
        """
        def validate(self, value, model_instance):
            """
            Validate that all the nested child fields pass validation
            """
            # pylint:disable=bad-super-call
            # ArrayField.validate is broken, so skip over it and call the
            # grandparent super method. The code below is a working replacement
            # of ArrayField.validate
            super(BaseArrayField, self).validate(value, model_instance)
            # pylint:enable=bad-super-call
            for i, part in enumerate(value):
                try:
                    self.base_field.validate(part, model_instance)
                except ValidationError as err:
                    raise prefix_validation_error(
                        err, self.error_messages['item_invalid'],
                        code='item_invalid',
                        params={'nth': i})
            if isinstance(self.base_field, BaseArrayField):
                if len({len(i) for i in value}) > 1:
                    raise ValidationError(
                        self.error_messages['nested_array_mismatch'],
                        code='nested_array_mismatch',
                    )

        def run_validators(self, value):
            """
            Run the validators for all the child fields
            """
            # pylint:disable=bad-super-call
            # ArrayField.validate is broken, so skip over it and call the
            # grandparent super method. The code below is a working replacement
            # of ArrayField.validate
            super(BaseArrayField, self).run_validators(value)
            # pylint:enable=bad-super-call
            for i, part in enumerate(value):
                try:
                    self.base_field.run_validators(part)
                except ValidationError as err:
                    raise prefix_validation_error(
                        err, self.error_messages['item_invalid'],
                        code='item_invalid',
                        params={'nth': i})
