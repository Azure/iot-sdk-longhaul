# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import string
import random
import uuid


@pytest.fixture(scope="session")
def random_string_factory():
    def factory_function(length=64):
        return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))

    return factory_function


@pytest.fixture(scope="function")
def random_string(random_string_factory):
    return random_string_factory()


@pytest.fixture(scope="session")
def random_dict_factory(random_string_factory):
    def factory_function():
        return {
            "random_guid": str(uuid.uuid4()),
            "sub_object": {
                "string_value": random_string_factory(),
                "bool_value": random.random() > 0.5,
                "int_value": random.randint(-65535, 65535),
            },
        }

    return factory_function


@pytest.fixture(scope="function")
def random_dict(random_dict_factory):
    return random_dict_factory()


@pytest.fixture(
    params=[
        pytest.param("int", id="integer value"),
        pytest.param("bool", id="boolean value"),
        pytest.param("str", id="string value"),
        pytest.param("dict", id="complex value"),
        pytest.param("guid", id="guid value"),
    ]
)
def random_property_value(request, random_dict_factory, random_string_factory):
    param = request.param
    if param == "int":
        return random.randint(-65535, 65535)
    elif param == "bool":
        return random.random() > 0.5
    elif param == "str":
        return random_string_factory()
    elif param == "dict":
        return random_dict_factory()
    elif param == "guid":
        return str(uuid.uuid4())
