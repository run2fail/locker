#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from colorama import Fore
import iptc
import re

regex_valid_identifier = r'[a-zA-Z][a-zA-Z\d]*'
regex_project_name = r'^(?P<project>' +  regex_valid_identifier + r')$'
regex_container_name = regex_project_name[0:-1] + r'_(?P<container>' + regex_valid_identifier + ')$'
regex_link = r'^(?P<name>' + regex_valid_identifier + r')(?::(?P<alias>' + regex_valid_identifier + r'))?$'
regex_ip = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'
regex_ports = r'^(?:(?P<host_ip>' + regex_ip + '):)?(?P<host_port>\d{1,5}):(?P<container_port>\d{1,5})(?:/(?:(?P<proto_udp>udp)|(?P<proto_tcp>tcp)))?$'
regex_volumes = r'^(?P<outside>.*):/(?P<inside>.*)$'
regex_cgroup = r'^(?P<key>.*)\s*=\s*(?P<value>.*)$'

def expand_vars(text, container):
    ''' Expand some variables

    :param text: The string with variables to expand
    :param container: Container instance to access the replacement strings
    :returns: Expanded string
    '''
    text = text.replace('$name', container.name.split('_')[1])
    text = text.replace('$project', container.project.name)
    if 'fqdn' in container.yml and container.yml['fqdn']:
        text = text.replace('$fqdn', container.yml['fqdn'])
    elif '$fqdn' in text:
        container.logger.warn('Cannot replace undefined $fqdn in: %s', text)
    return text

def break_and_add_color(container, vals):
    ''' Break a list of string into colored lines

    :param container: Container instance (used for colored output)
    :param vals: List of string to break in multiple lines
    '''
    if not vals:
        return ''
    reset_color = Fore.RESET if container.color else ''
    return '\n'.join(['%s%s%s' % (container.color, v, reset_color) for v in vals])

def rule_to_str(rule):
    ''' Human readable representation of iptc.Rule

    This function should be in the iptc module.
    TODO Should be cleaned up or reimplemented
    '''
    def params2str(params):
        return ' '.join(['%s:%s' % (k, ','.join(v)) for k,v in params.items()])

    try:
        target = rule.target.name
        target_params = ' '.join(['%s: %s' % (k,v) for k,v in rule.target.parameters.items()])
    except AttributeError:
        target = ''
        target_params = ''

    protocol = 'all' if not rule.protocol else rule.protocol
    if_in = 'any' if not rule.in_interface else rule.in_interface
    if_out = 'any' if not rule.out_interface else rule.out_interface
    src = 'anywhere' if rule.src == '0.0.0.0/0.0.0.0' else rule.src
    dst = 'anywhere' if rule.dst == '0.0.0.0/0.0.0.0' else rule.dst
    match_str = list()
    for match in [match for match in rule.matches if match.name != 'comment']:
        name = match.name
        params = params2str(match.get_all_parameters())
        match_str.append('%s %s' % (name, params))
    match_str = ' '.join(match_str)
    return 'target=%s %s | proto=%s | if=%s of=%s | src=%s dst=%s | match=%s' % (target, target_params, protocol, if_in, if_out, src, dst, match_str)

def rules_to_str(dnat_rules):
    ''' Convert tuple of DNAT rules to list of strings

    :param dnat_rules: tripel of (proto, (dip, dport), (to_ip, to_port))
    :returns: Rules as list of (sorted) strings
    '''
    rules = list()
    for proto, (dip, dport), (to_ip, to_port) in dnat_rules:
        dip, mask = dip.split('/')
        if dip == '0.0.0.0':
            rule = '%s->%s/%s' % (dport, to_port, proto)
        else:
            rule = '%s:%s->%s/%s' % (dip, dport, to_port, proto)
        rules.append(rule)
    return sorted(rules)
