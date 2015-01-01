'''
A parser and manager for the /etc/hosts file
'''

import logging
import re

import netaddr
import prettytable


class InvalidLine(Exception):
    pass

class DuplicateIP(ValueError):
    pass

class IPNotFound(ValueError):
    pass

class HostsRow(object):
    ''' Internal representation of a line in the hosts file
    '''

    # "Host names may contain only alphanumeric characters, minus signs ("-"),
    # and periods (".").  They must begin with an alphabetic character and
    # end with an alphanumeric character" see "man hosts"
    regex_disabled  = r'\s*#+'
    regex_ip        = r'[\da-fA-F\:\.]+'
    regex_name      = r'[a-zA-Z\d][a-zA-Z\d\-\.]*[a-zA-Z\d]'
    regex_name_lax  = r'[a-zA-Z\d][a-zA-Z\d\-\.\_]*[a-zA-Z\d]'
    regex_names     = r'(?:' + regex_name + ')(?:\s+' + regex_name + ')*'
    regex_names_lax = r'(?:' + regex_name_lax + ')(?:\s+' + regex_name_lax + ')*'
    regex_comment   = r'.*'

    def __init__(self, num, raw):
        ''' Initialize the member variables and start parsing
        '''
        self.num = int(num)
        self.raw = raw.replace('\t', ' ').strip()
        self._ip = None
        self._names = None
        self.comment = None
        self.is_deactivated = False
        self.is_comment = False
        self.is_empty = False

    @property
    def ip(self):
        return self._ip

    @ip.setter
    def ip(self, value):
        if isinstance(value, str):
            value = netaddr.IPAddress(value)
        elif isinstance(value, netaddr.IPAddress):
            pass
        else:
            raise TypeError('\"ip\" has an invalid type: %s' % (type(value)))
        self._ip = value

    @property
    def names(self):
        return self._names

    @names.setter
    def names(self, value):
        if isinstance(value, str):
            value = [value]
        elif isinstance(value, list):
            pass
        else:
            raise TypeError('\"names\" has an invalid type: %s' % (type(value)))
        regex = re.compile(HostsRow.regex_name)
        for name in value:
            match = regex.match(name)
            if not match:
                raise ValueError('Invalid name: %s' % name)
        self._names = value

    @classmethod
    def parse(cls, num, raw, lax=False):
        '''
        :param lax: allow some invalid characters in hostnames
        '''
        hosts = cls(num, raw)
        hosts._parse(lax)
        return hosts

    @classmethod
    def new(cls, ip, names, comment=None):
        hosts = cls(-1, '')
        if isinstance(ip, netaddr.IPAddress):
            hosts.ip = ip
        else:
            hosts.ip = netAddr.IPAddress(ip)
        hosts.names = names
        hosts.comment = comment
        return hosts

    def __str__(self):
        return '%4d: %s %s # %s' % (self.num, self.ip, ' '.join(self.names), self.comment)

    def __repr__(self):
        return 'HostsRow: %s %s %s %s' % (self.num, self.ip, self.names, self.comment)

    def __lt__(self, other):
        if not self.ip:
            return True
        if not other.ip:
            return False
        if self.ip.version < other.ip.version:
            return True
        return self.ip < other.ip

    def _parse(self, lax=False):
        ''' Parse and analyze the line
        '''
        line = self.raw

        regex_names = HostsRow.regex_names
        if lax:
            regex_names = HostsRow.regex_names_lax
        regex = r'^(?P<disabled>' + HostsRow.regex_disabled +')?\s*(?P<ip>' + HostsRow.regex_ip + ')\s+(?P<names>' + regex_names + ')(?:\s+#+\s*(?P<comment>' + HostsRow.regex_comment + ')\s*)?$'
        match = re.compile(regex).match(self.raw)
        if match:
            # normal entry
            groupdict = match.groupdict()
            self.is_deactivated = True if groupdict['disabled'] else False
            try:
                ip = netaddr.IPAddress(groupdict['ip'])
            except netaddr.AddrFormatError:
                raise InvalidLine('Invalid IP address in line %d: %s' % (self.num, groupdict['ip']))
            self.ip = ip
            self.comment = groupdict['comment']
            self.names = groupdict['names'].split(' ')
        elif line.startswith('#'):
            # whole line is a comment
            self.is_comment = True
        elif len(line) == 0:
            # blank line
            self.is_empty = True
        else:
            raise InvalidLine('Line %d is neither a valid entry nor a comment: %s' % (self.num, self.raw))

    def to_list(self):
        if self.is_empty:
            return (['','',''])
        elif self.is_comment:
            return ('', '', self.raw)
        elif self.comment:
            return ((self.ip, ' '.join(self.names), ' # %s' % self.comment))
        else:
            return ((self.ip, ' '.join(self.names), ''))


class Hosts(object):
    ''' Parses and modifies /etc/hosts
    '''

    def __init__(self, infile='/etc/hosts', logger=None, lax=False):
        ''' Initializes the class and trigger the parsing

        :param infile: The hosts file to parse
        :param logger: custom logging instance
        :param lax: Allow additional characters when parsing
        '''
        if not logger:
            self.logger = logging.getLogger(self.__class__.__name__)
        else:
            self.logger = logger
        try:
            with open(infile, 'r') as hfile_fd:
                self.hosts = infile
        except FileNotFoundError:
            self.logger.error('Hosts file was not found: %s', infile)
            raise
        except PermissionError:
            self.logger.error('Do not have permission to read host file: %s', infile)
            raise
        self.hosts_file = infile
        self.rows = list()
        self._parse(lax)

    def __str__(self):
        return self.pprint()

    def __repr__(self):
        return '\n'.join([l.__repr__() for l in self.rows])

    def _parse(self, lax=False):
        ''' Parse the hosts file '''
        with open(self.hosts, 'r') as hfile_fd:
            for line_num, line in enumerate(hfile_fd.readlines()):
                self.rows.append(HostsRow.parse(line_num, line, lax=True))

    def get_row(self, ip):
        ''' Search IP address
        '''
        if not isinstance(ip, netaddr.IPAddress):
            ip = netaddr.IPAddress(ip)
        for row in self.rows:
            if row.ip == ip:
                return row
        return None

    def add(self, ip, names, comment=None):
        ''' Add the IP with the specified names and comment
        '''
        if not isinstance(ip, netaddr.IPAddress):
            ip = netaddr.IPAddress(ip)
        if self.get_row(ip):
            raise DuplicateIP('Hosts file already contains: %s' % ip)
        row = HostsRow.new(ip, names, comment)
        self.rows.append(row)
        self.logger.debug('Added row: %s' % row)

    def remove_ip(self, ip):
        ''' Remove the given IP address
        '''
        if not isinstance(ip, netaddr.IPAddress):
            ip = netaddr.IPAddress(ip)
        if not self.get_row(ip):
            raise IPNotFound('Hosts file does not contain: %s' % ip)
        removed_rows = [l for l in self.rows if l.ip == ip]
        self.rows = [l for l in self.rows if l.ip != ip]
        for row in removed_rows:
            self.logger.debug('Removed rows: %s' % row)

    def update_ip(self, ip, names, comment=None):
        ''' Update the names for an IP address
        '''
        if not isinstance(ip, netaddr.IPAddress):
            ip = netaddr.IPAddress(ip)
        row = self.get_row(ip)
        if not row:
            raise IPNotFound('Hosts file does not contain: %s' % ip)
        row.names = names
        row.comment = comment
        self.logger.debug('Updated hosts entry: %s' % row)

    def remove_by_comment(self, comment):
        ''' Remove all rows with matching comments

        Comment may also be a regex. The re module is used for the matching in
        all cases.

        :param comment: Rows matching this comment will be removed. May be in
                        re modules regex format. You must specify line start "^"
                        and line end "$" in comment to avoid removing lines where
                        an infix matches your regex.
        :returns: Number of removed lines
        '''
        regex = re.compile(comment)
        filtered_rows = list()
        removed = 0
        for row in self.rows:
            if row.comment and regex.match(row.comment):
                self.logger.debug('Removing row: %s' % row)
                removed += 1
                continue
            filtered_rows.append(row)
        self.rows = filtered_rows
        return removed

    def pprint(self):
        ''' Align/format rows

        :returns: Formatted rows as string
        '''
        header = ['IP', 'Names', 'Comment']
        table = prettytable.PrettyTable(header)
        table.align = 'l'
        table.border = False
        table.header = False
        for row in self.rows:
            table.add_row(row.to_list())
        output = '\n'.join([row.strip() for row in table.get_string().split('\n')])
        return output

    def save(self, outfile=None):
        ''' Save content to file

        :param outfile: Destination file to write content, falls back to the
                        filename provided to the init function if None.
        '''
        if not outfile:
            outfile = self.hosts_file
        with open(outfile, 'w') as out_fd:
            out_fd.write(self.pprint())
            out_fd.write('\n')
