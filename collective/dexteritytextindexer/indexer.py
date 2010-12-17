from collective.dexteritytextindexer import interfaces
from collective.dexteritytextindexer.behavior import IDexterityTextIndexer
from collective.dexteritytextindexer.directives import SEARCHABLE_KEY
from five import grok
from plone.dexterity.utils import iterSchemata
from plone.indexer import indexer
from plone.z3cform import z2
from z3c.form.field import Field
from z3c.form.interfaces import DISPLAY_MODE, IFieldWidget
from z3c.form.interfaces import IContextAware, IFormLayer, IField
from zope import schema
from zope.component import getAdapters, getMultiAdapter
from zope.interface import alsoProvides


@indexer(IDexterityTextIndexer)
def dynamic_searchable_text_indexer(obj):
    """Dynamic searchable text indexer.
    """

    # We need to make sure that we have z2 moe switched on for z3c form.
    # Since we do not really have any view to do this on, we just use
    # the "view" view, which usually exists. It's not necessary that
    # the view points to a z3cform, only view.request is used..
    view = obj.restrictedTraverse('view')
    z2.switch_on(view, request_layer=IFormLayer)

    indexed = []

    for storage, fields in get_searchable_contexts_and_fields(obj):
        for field in fields:

            # we need the form-field, not the schema-field we
            # already have..
            form_field = Field(field, interface=field.interface,
                               prefix='')

            # get the widget
            widget = get_field_widget(obj, form_field)

            # get the converter for this field / widget
            converter = getMultiAdapter(
                (obj, field, widget),
                interfaces.IDexterityTextIndexFieldConverter)

            # convert the field value
            value = converter.convert()

            # if no value was returned, we don't need to index
            # anything.
            if not value:
                continue

            # be sure that it is utf-8 encoded
            if isinstance(value, unicode):
                value = value.encode('utf-8')

            # only accept strings
            assert isinstance(value, str), 'expected converted ' + \
                'value of IDexterityTextIndexFieldConverter to be a str'

            indexed.append(value)

    # after converting all fields, run additional
    # IDynamicTextIndexExtender adapters.
    for name, adapter in getAdapters(
        (obj,), interfaces.IDynamicTextIndexExtender):
        extended_value = adapter()

        # if no value was returned, we don't need to index anything.
        if not extended_value:
            continue

        # be sure that it is utf-8 encoded
        if isinstance(extended_value, unicode):
            extended_value = extended_value.encode('utf-8')

        # only accept strings
        assert isinstance(extended_value, str), 'expected converted ' + \
            'value of IDynamicTextIndexExtender to be a str'

        indexed.append(extended_value)

    return ' '.join(indexed)


grok.global_adapter(dynamic_searchable_text_indexer,
                    name='SearchableText')


def get_field_widget(obj, field):
    """Returns the field widget of a field in display mode without
    touching any form.
    The `field` should be a z3c form field, not a zope schema field.
    """

    assert IField.providedBy(field), 'field is not a form field'

    if field.widgetFactory.get(DISPLAY_MODE) is not None:
        factory = field.widgetFactory.get(DISPLAY_MODE)
        widget = factory(field.field, obj.REQUEST)
    else:
        widget = getMultiAdapter(
            (field.field, obj.REQUEST), IFieldWidget)
    widget.name = '' + field.__name__  # prefix not needed
    widget.id = widget.name.replace('.', '-')
    widget.context = obj
    alsoProvides(widget, IContextAware)
    widget.mode = DISPLAY_MODE
    widget.update()
    return widget


def get_searchable_contexts_and_fields(obj):
    """Returns a generator of tuples, which contains a storage object for
    each schema (adapted `obj`) and a list of fields on this schema which
    are searchable.
    """

    for schemata in iterSchemata(obj):
        fields = []
        tagged_values = schemata.queryTaggedValue(SEARCHABLE_KEY)
        if not tagged_values:
            continue

        for i, name, v in tagged_values:
            fields.append(schema.getFields(schemata).get(name))

        if fields:
            storage = schemata(obj)
            yield storage, fields
