from pyqtgraph.Qt.QtWidgets import *
from pyqtgraph import parametertree
from thefuzz import fuzz
from proto.import_all_protos import *
import netifaces


"""
Instead of the using the generic parameter parsing, this constant can be used to define custom handlers for specific
fields in the proto.

To define a custom handler:
    1. The key is the name of the field in the proto
    2. The value is the function that will be called to parse the field. Make sure the function is callable from this
       file
"""
CUSTOM_PARAMETERS_OVERRIDE = {
    "robot_communication_interface": "__create_network_enum",
    "referee_interface": "__create_network_enum",
    "vision_interface": "__create_network_enum",
}


def __create_int_parameter_writable(key, value, descriptor):
    """Converts an int field of a proto to a NumericParameterItem with
    the min/max bounds set according to the provided ParameterRangeOptions

    min/vax options.

    :param key: The name of the parameter
    :param value: The default value
    :param descriptor: The proto descriptor
    """
    # Extract the options from the descriptor, and store it
    # in the dictionary.
    options = descriptor.GetOptions()

    try:
        minimum, maximum = (
            options.Extensions[bounds].min_int_value,
            options.Extensions[bounds].max_int_value,
        )
    except KeyError:
        raise KeyError("{} missing ParameterRangeOptions".format(key))

    return {
        "name": key,
        "type": "int",
        "value": value,
        "default": value,
        "limits": (int(minimum), int(maximum)),
        "step": 1,
    }


def __create_double_parameter_writable(key, value, descriptor):
    """Converts a double field of a proto to a NumericParameterItem with
    the min/max bounds set according to the provided ParameterRangeOptions
    min/vax options.

    :param key: The name of the parameter
    :param value: The default value
    :param descriptor: The proto descriptor
    """
    # Extract the options from the descriptor, and store it
    # in the dictionary.
    options = descriptor.GetOptions()

    try:
        minimum, maximum = (
            options.Extensions[bounds].min_double_value,
            options.Extensions[bounds].max_double_value,
        )
    except KeyError:
        raise KeyError("{} missing ParameterRangeOptions".format(key))

    return {
        "name": key,
        "type": "float",
        "value": value,
        "default": value,
        "limits": (
            minimum,
            maximum,
        ),
        "step": 0.01,
    }


def __create_enum_parameter(key, value, descriptor):
    """Converts an enum field in a protobuf to a ListParameter. Uses
    the options to lookup all possible enum values and provides them
    as a dropdown option.

    :param key: The name of the parameter
    :param value: The default value
    :param descriptor: The proto descriptor
    """
    options = []

    for enum_desc in descriptor.enum_type.values:
        options.append(enum_desc.name)

    # The list index is indexed from 1
    current_enum_index = value - 1

    return parametertree.parameterTypes.ListParameter(
        name=key,
        default=None,
        value=descriptor.enum_type.values[current_enum_index].name,
        limits=options,
    )


def __create_bool_parameter(key, value, _):
    """Convert a bool field in proto to a BoolParameter

    :param key: The name of the parameter
    :param value: The default value
    :param _: The proto descriptor, unused for bool
    """
    return {"name": key, "type": "bool", "value": value}


def __create_string_parameter_writable(key, value, descriptor):
    """Convert a string field in proto to a StrParameter

    :param key: The name of the parameter
    :param value: The default value
    :param descriptor: The proto descriptor
    """
    return {"name": key, "type": "text", "value": " "}


def __create_parameter_read_only(key, value, descriptor):
    """Convert a string field in proto to a read only Str Parameter

    :param key: The name of the parameter
    :param value: The default value
    :param descriptor: The proto descriptor
    """
    return {"name": key, "type": "str", "value": value, "readonly": True}


def __create_network_enum(key, value, _):
    """Lists all the network interfaces available on the system as enum options for the given parameter field.

    :param key: The name of the parameter
    :param value: The default value
    """
    network_interfaces = netifaces.interfaces()

    return parametertree.parameterTypes.ListParameter(
        name=key, default=None, value=value, limits=network_interfaces
    )


def get_string_val(descriptor, value):
    """Converts the given value to a string depending on the descriptor type

    :param descriptor: the descriptor of the current value
    :param value: the value to convert
    :return: A string version of the value
    """
    if descriptor.type in [
        descriptor.TYPE_DOUBLE,
        descriptor.TYPE_FLOAT,
    ]:
        return "%.2f" % value
    elif descriptor.type == descriptor.TYPE_ENUM:
        if type(value) == int:
            return descriptor.enum_type.values[value].name
        elif descriptor.label == descriptor.LABEL_REPEATED:
            return str([descriptor.enum_type.values[index].name for index in value])
    else:
        return str(value)


def config_proto_to_field_list(
    message, read_only=False, search_term=None, search_filter_threshold=60
):
    """Converts a protobuf to a pyqtgraph parameter tree dictionary
    that can loaded directly into a ParameterTree

    https://pyqtgraph.readthedocs.io/en/latest/parametertree/index.html

    :param message: The message to convert to a dictionary
    :param read_only: Whether the parameters should be read only or writable
    :param search_term: The search filter
    :param search_filter_threshold: the search filter threshold
    """
    field_list = []

    for descriptor in message.DESCRIPTOR.fields:
        key = descriptor.name
        value = getattr(message, descriptor.name)

        if search_term and descriptor.type != descriptor.TYPE_MESSAGE:
            if fuzz.partial_ratio(search_term, key) < search_filter_threshold:
                continue

        if descriptor.name in CUSTOM_PARAMETERS_OVERRIDE.keys():
            field_list.append(
                eval(CUSTOM_PARAMETERS_OVERRIDE[descriptor.name])(
                    key, value, descriptor
                )
            )
        elif descriptor.type == descriptor.TYPE_MESSAGE:
            field_list.append(
                {
                    "name": key,
                    "type": "group",
                    "children": config_proto_to_field_list(
                        value,
                        read_only=read_only,
                        search_term=search_term,
                        search_filter_threshold=search_filter_threshold,
                    ),
                }
            )

        elif read_only:
            field_list.append(
                __create_parameter_read_only(
                    key, get_string_val(descriptor, value), descriptor
                )
            )

        elif descriptor.type == descriptor.TYPE_BOOL:
            field_list.append(__create_bool_parameter(key, value, descriptor))

        elif descriptor.type == descriptor.TYPE_ENUM:
            field_list.append(__create_enum_parameter(key, value, descriptor))

        elif descriptor.type == descriptor.TYPE_STRING:
            field_list.append(
                __create_string_parameter_writable(key, value, descriptor)
            )

        elif descriptor.type in [descriptor.TYPE_DOUBLE, descriptor.TYPE_FLOAT]:
            field_list.append(
                __create_double_parameter_writable(key, value, descriptor)
            )

        elif descriptor.type in [
            descriptor.TYPE_INT32,
            descriptor.TYPE_INT64,
            descriptor.TYPE_UINT32,
            descriptor.TYPE_UINT64,
        ]:
            field_list.append(__create_int_parameter_writable(key, value, descriptor))

        else:
            raise NotImplementedError(
                "Unsupported type {} in parameter config".format(descriptor.type)
            )

    if field_list:
        return field_list

    return {}
