import logging

from django.contrib.auth.models import Group
from django.contrib.gis.geos import GEOSGeometry
from geostore.models import Layer, LayerGroup
from terra_geocrud.models import CrudView, CrudViewProperty
from terra_geocrud.properties.schema import sync_layer_schema
from rest_framework.exceptions import MethodNotAllowed

from custom.receivers import *  # noqa

logger = logging.getLogger(__name__)


def layer_callback(geosource):

    group_name = geosource.settings.pop('group', 'reference')

    defaults = {
        'settings': geosource.settings,
    }

    layer, _ = Layer.objects.get_or_create(name=geosource.slug, defaults=defaults, geom_type=geosource.geom_type)

    layer_groups = Group.objects.filter(pk__in=geosource.settings.get('groups', []))

    crud_view = CrudView.objects.get_or_create(layer=layer,
                                               defaults={"name": layer.name, "order": 0})[0]

    fields = geosource.fields.all()
    for field in fields:
        data_type = field.data_type
        name = field.name
        label = field.label
        if data_type == 1:
            final_type = "string"
        elif data_type == 2:
            final_type = "string"
        elif data_type == 3:
            final_type = "float"
        elif data_type == 4:
            final_type = "boolean"
        property, created = CrudViewProperty.objects.get_or_create(view=crud_view, key=name)
        property.json_schema = {"title": label, "type": final_type}
        property.save()

    sync_layer_schema(crud_view)
    if set(layer.authorized_groups.all()) != set(layer_groups):
        layer.authorized_groups.set(layer_groups)

    if not layer.layer_groups.filter(name=group_name).exists():
        group, _ = LayerGroup.objects.get_or_create(name=group_name)
        group.layers.add(layer)

    return layer


def feature_callback(geosource, layer, identifier, geometry, attributes):
    # Force converting geometry to 4326 projection
    try:
        geom = GEOSGeometry(geometry)
        geom.transform(4326)
        return layer.features.update_or_create(identifier=identifier,
                                               defaults={'properties': attributes, 'geom': geom})[0]
    except TypeError:
        logger.warning(f'One record was ignored from source, because of invalid geometry: {attributes}')
        return None


def clear_features(geosource, layer, begin_date):
    return layer.features.filter(updated_at__lt=begin_date).delete()


def delete_layer(geosource):
    if geosource.layers.count() > 0:
        raise MethodNotAllowed('No layers must be linked to this source to be deleted')
    geosource.get_layer().features.all().delete()
    return geosource.get_layer().delete()
