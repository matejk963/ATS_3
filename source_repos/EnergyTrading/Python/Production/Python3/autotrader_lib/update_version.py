# coding: utf-8

"""
This script bumps the version of autotrader in the autotrader_lib.version.py file
and commits the change automatically.
It is intended to be run when releasing a new version and is triggered
in the release job of the pipeline.
"""

from __future__ import print_function

import json
import pkg_resources
import re
import requests


class VersionCheckProblem(Exception):
    """Problem with version"""
    pass


AT_PROJECT_ID = 36
ADDRESS = "git.visotech.at"
TOKEN = "QBrsbqnuA_m6NCCLrknD"
FILE_PATH = "autotrader_lib/version.py"
FILE_CONTENT = "VERSION=\"{}\"\n"


def _gitlab_request(path, address=ADDRESS, token=TOKEN, data=None):
    """Send post request to gitlab"""
    headers = {"PRIVATE-TOKEN": token,
               "Content-Type": "application/json"}
    url = "https://{}/api/v4{}".format(address, path)
    return requests.post(url, headers=headers, data=data)


def increase_version(version):
    """Increase patch version

    :param version: a list in the format ["major", "minor", "(RC) patch"]
    :type version: list(str)

    :return: next version
    :rtype: str
    """

    increase = version.pop()
    if increase.startswith("RC"):
        increase = "RC{}".format(int(increase.split("RC")[1]) + 1)
    else:
        increase = str(int(increase) + 1)
    return ".".join(version + [increase])


def current_autotrader_version():
    """Get the autotrader version from the version file"""
    with open(FILE_PATH, "r") as fo:
        existing_content = fo.read()
    ver = re.findall("\"([^\"]*)\"", existing_content)
    if ver:
        return ver[0]
    raise VersionCheckProblem("could not parse autotrader version from file")


def _parse_version(version):
    """Check and parse a version string and return it as a list"""
    check = re.search(r"^V?([0-9]+\.[0-9]+\.(?:[0-9]|RC[0-9])+)$", version)
    if check:
        return check.groups()[0].split(".")
    raise VersionCheckProblem("could not parse {}".format(version))


def update_version(version, branch, verbose):
    """Bumps autotrader version and commits the change through the gitlab rest api

    :param version: Version that is currently being released
    :type version: str
    :param branch: Branch in which the version is currently being released
    :type version: str
    :param verbose: Prints a message when the new version is commited
    :type verbose: bool

    :return: returns a commit instruction that can be sent to gitlab
    """
    if not version:
        raise VersionCheckProblem("version is missing")
    if not branch:
        raise VersionCheckProblem("branch is missing")
    at_version = current_autotrader_version()
    if pkg_resources.parse_version(at_version.lstrip("V")) > pkg_resources.parse_version(version.lstrip("V")):
        raise VersionCheckProblem("autoTRADER version {} is higher than the tag {}".format(at_version, version))

    next_version = increase_version(_parse_version(version))
    file_content = FILE_CONTENT.format(next_version)
    api_action = {
        "branch": branch,
        "commit_message": "update version",
        "actions": [{"action": "update",
                     "file_path": FILE_PATH,
                     "content": file_content}]
    }
    response = _gitlab_request(path="/projects/{}/repository/commits".format(AT_PROJECT_ID),
                               data=json.dumps(api_action))
    if verbose:
        print("Status: ", response.status_code)
        print(response.json())
    if response.status_code != 201:
        print("Cannot increase the autoTRADER version")
    return response


def main():
    """Parses the arguments and updates autotrader version based on that"""
    import argparse
    parser = argparse.ArgumentParser(description="Update autotrader version.")
    parser.add_argument("-t", "--tag", default=None, dest="version",
                        help="specifies the version of the build")
    parser.add_argument("-b", "--branch", default=None, dest="branch",
                        help="specifies the branch")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose mode. Print executed git commands")
    args = parser.parse_args()
    update_version(args.version, args.branch, args.verbose)


if __name__ == "__main__":
    main()
