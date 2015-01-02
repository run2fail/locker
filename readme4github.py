#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
Github does not support "include" in Restructured Text files due to security
concerns. This script merges all files included in "README.tmpl" into
"README.rst".
'''

import re

def merge(included, readme_out):
    with open(included, 'r') as included_fd:
        for in_line in included_fd.readlines():
            readme_out.write(in_line)
    readme_out.write('\n\n')

def main():
    regex = re.compile(r'^.. include:: (.*)$')
    with open('./README.tmpl', 'r') as readme_in, \
            open('./README.rst', 'w+') as readme_out:
        for in_line in readme_in.readlines():
            match = regex.match(in_line)
            if match:
                merge(match.group(1), readme_out)
            else:
                readme_out.write(in_line)

if __name__ == '__main__':
    main()