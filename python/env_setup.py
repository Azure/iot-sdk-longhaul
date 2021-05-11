# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
"""Prepare development environment
"""

import sys
from subprocess import check_call, CalledProcessError


def pip_command(command, error_ok=False):
    try:
        print("Executing: " + command)
        check_call([sys.executable, "-m", "pip"] + command.split())
        print()

    except CalledProcessError as err:
        print(err)
        if not error_ok:
            sys.exit(1)


packages = ["device", "service"]
editable_packages = ["common"]


if __name__ == "__main__":
    # Make sure pip is on the latest version
    pip_command("install --upgrade pip")

    # Install packages
    for package_name in editable_packages:
        # Use an eager upgrade strategy to make sure we have all the latest dependencies.
        # This way we will be running into any dependency-related bugs before customers do.
        pip_command("install -U --upgrade-strategy eager -e {}".format(package_name))

    for package_name in packages:
        pip_command(
            "install -U --upgrade-strategy eager -r {}/requirements.txt".format(package_name)
        )

    # Install testing environment dependencies
    pip_command("install -U -r requirements_dev.txt")
