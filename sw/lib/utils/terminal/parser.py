# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging
from pathlib import Path

from sw.lib.utils.iclab_session import prompt_for_credentials, get_credentials_from_keyfile
from sw.lib.utils.crypto import Credentials

logger = logging.getLogger(__name__)

class BaseParser:
    def __init__(self, args=None):
        self.parser = argparse.ArgumentParser(description='Gets options from command line.')
        self.init_parser()
        self.args = self.parser.parse_args(args) if args else self.parser.parse_args()
        self.check_args()
        self.init_attr()
        self.reduce_args()

    def init_parser(self):
        raise NotImplementedError

    def check_args(self):
        raise NotImplementedError

    def init_attr(self):
        pass

    def reduce_args(self):
        raise NotImplementedError


class Parser(BaseParser):
    def __init__(self, ):
        super().__init__()

    def init_parser(self):
        self.parser.add_argument('-k', '--keyfile', type=Path, help='Key file path')
        self.parser.add_argument('-u', '--username', type=str, help='University username')
        self.parser.add_argument('-p', '--password', type=str, help='University password')
        self.parser.add_argument('-f', '--config-file', type=Path, help='Configuration file path')
        self.parser.add_argument('-v', '--verbose', action='count', default=0,
            help='Enable verbose output')
        self.parser.add_argument('-i', '--interactive', action='store_true',
            help='Enable interactive mode for user input during execution')

    def _check_file_arg(self, arg_name):
        arg_value = getattr(self.args, arg_name)
        if arg_value is not None and not Path.is_file(arg_value):
            logger.error(f'File {arg_value} not found')
            raise FileNotFoundError

    def check_args(self):
        # Check if the keyfile argument is provided and if the file exists
        self._check_file_arg('keyfile')
        self._check_file_arg('config_file')

    def reduce_args(self):
        # Getting the credentials from the keyfile if provided
        if self.args.keyfile is not None:
            self._credentials = get_credentials_from_keyfile(self.args.keyfile)
        elif self.args.username is not None and self.args.password is not None:
            self._credentials = Credentials(self.args.username, self.args.password)
        else:
            self._credentials = prompt_for_credentials()

    def get_credentials(self):
        return self._credentials

    # Logging related methods
    # TODO DEBT: logging related building should be moved to a separate class
    #    i.e. a separate logging wrapper
    def get_logging_level(self):
        if self.args.verbose == 0:
            return logging.WARNING
        elif self.args.verbose == 1:
            return logging.INFO
        else:
            return logging.DEBUG

    def get_logging_format(self):
        if self.args.verbose == 0:
            return '[%(levelname)s]: %(message)s'
        elif self.args.verbose == 1:
            return '[%(levelname)s]: %(message)s'
        else:
            return (
                '[%(asctime)s] [%(filename)s - %(funcName)s +%(lineno)s]\n'
                '\t[%(levelname)s]: %(message)s'
            )

    def get_verbose(self):

        if self.args.verbose > 1:
            return True
        else:
            return False
