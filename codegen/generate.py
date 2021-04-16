# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import yaml
import argparse
import abc
import json


class BaseGenerator(abc.ABC):
    """
    Abstract base class for all generator objects
    """

    def include_group(self, group):
        """
        Return True to include this group when generating code.
        """
        return True

    @abc.abstractmethod
    def dump_group_header(self, group):
        """
        Dumps the header for a "Group:" entry
        """
        pass

    @abc.abstractmethod
    def dump_group_value(self, value):
        """
        Dumps a top level group value
        """
        pass

    @abc.abstractmethod
    def dump_subgroup_header(self, subgroup):
        """
        Dumps the header for a "Subgroup:" entry
        """
        pass

    def dump_subgroup_value(self, value):
        """
        Dumps a sub-group value
        """
        # by default subgroup values get dumped the same way as group values
        self.dump_group_value(value)


def dashes(count):
    """
    Return the specified number of dashes as a string
    """
    return "".join(("-" for _ in range(0, count)))


class PythonBaseGenerator(BaseGenerator):
    """
    Base class for all python generators
    """

    def dump_subgroup_header(self, subgroup):
        print("")
        text = subgroup.get("desc", None) or subgroup.get("name", None)
        if text:
            print("    # {}".format(dashes(len(text))))
            print("    # {}".format(text))
            print("    # {}".format(dashes(len(text))))


class PythonConstantsGenerator(PythonBaseGenerator):
    """
    Generator for thief_constants.py
    """

    def dump_group_header(self, group):
        print("class {}(object):".format(group["name"]))
        if "desc" in group:
            print('    """')
            print("    {}".format(group["desc"]))
            print('    """')
        print("")

        # Yield to allow calling code to print everything in the group before continuing
        yield

        print("")
        print("")

    def dump_group_value(self, value):
        if "desc" in value:
            print("")
            print("    # {}".format(value["desc"]))
        print("    {} = {}".format(value["name"], json.dumps(value["value"])))


class PythonConfigureMetricsGenerator(PythonBaseGenerator):
    """
    Generator for python metrics code
    """

    def include_group(self, group):
        return group.get("sendToAzureMonitor", "") in [True, "True", "true"]

    def dump_group_header(self, group):
        pass

    def dump_group_value(self, value):
        if value["type"] == "int":
            print("    self.reporter.add_integer_measurement(")
        elif value["type"] == "float":
            print("    self.reporter.add_float_measurement(")
        else:
            raise ValueError("Value {} is missing a type".format(value["name"]))

        print("        Const.{},".format(value["name"]))
        print('        "{}",'.format(value["desc"]))
        print('        "{}",'.format(value["units"]))
        print("        )")


def print_prefix(gen):
    if gen:
        try:
            next(gen)
        except StopIteration:
            pass


def print_suffix(gen):
    if gen:
        try:
            next(gen)
        except StopIteration:
            pass


def generate_thief_constants(constants, generator):
    for group in constants["groups"]:
        if generator.include_group(group):

            group_generator = generator.dump_group_header(group)
            print_prefix(group_generator)

            if "values" in group:
                for value in group["values"]:
                    generator.dump_group_value(value)

            if "subgroups" in group:
                for subgroup in group["subgroups"]:
                    subgroup_generator = generator.dump_subgroup_header(subgroup)
                    print_prefix(subgroup_generator)
                    for value in subgroup["values"]:
                        generator.dump_subgroup_value(value)
                    print_suffix(subgroup_generator)

            print_suffix(group_generator)


generators = {
    "python-constants": PythonConstantsGenerator,
    "python-configure-metrics": PythonConfigureMetricsGenerator,
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="generate")
    parser.description = "Generate code for longhaul constants"
    parser.add_argument(
        "generator", type=str, help="Code to generate", choices=list(generators.keys()),
    )

    args = parser.parse_args()

    with open("./constants.yaml") as f:
        constants = yaml.load(f, Loader=yaml.Loader)
    generator = generators[args.generator]()
    generate_thief_constants(constants, generator)
