# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

import argparse
from pathlib import Path

from .iclab_session import prompt_for_credentials, get_credentials_from_keyfile
from .crypto_utils import Credentials

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

    def set_defaults(self):
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
        self.parser.add_argument('--credentials', type=Credentials, help='Credentials in the format username:password')

    def set_defaults(self):
        pass

    def check_args(self):
        # Check if the keyfile argument is provided and if the file exists
        if self.args.keyfile is None:
            self.credentials = prompt_for_credentials()
        elif not Path.is_file(self.args.keyfile):
            print(f'File {self.args.keyfile} not found')
            raise FileNotFoundError

    def reduce_args(self):
        # Getting the credentials from the keyfile if provided
        if self.args.keyfile is not None:
            self.credentials = get_credentials_from_keyfile(self.args.keyfile)
