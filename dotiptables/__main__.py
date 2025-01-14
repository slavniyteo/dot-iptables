#!/usr/bin/python

import argparse
import errno
import os
import re
import subprocess
import sys

import jinja2
from jinja2.loaders import PackageLoader

BUILTIN_CHAINS = [
    'FORWARD',
    'INPUT',
    'OUTPUT',
    'POSTROUTING',
    'PREROUTING',
]

BUILTIN_TARGETS = [
    'ACCEPT',
    'RETURN',
    'DROP',
    'AUDIT',
    'CHECKSUM',
    'CLASSFY',
    'CLUSTERIP',
    'CONNMARK',
    'CONNSECMARK',
    'CT',
    'DNAT',
    'DNPT',
    'DSCP',
    'ECN',
    'HL',
    'HMARK',
    'IDLETIMER',
    'LED',
    'LOG',
    'MARK',
    'MASQUERADE',
    'NETMAP',
    'NFLOG',
    'NFQUEUE',
    'NOTRACK',
    'RATEEST',
    'REDIRECT',
    'REJECT',
    'SECMARK',
    'SET',
    'SNAT',
    'SNPT',
    'SYNPROXY',
    'TCPMSS',
    'TCPOPTSTRIP',
    'TEE',
    'TOS',
    'TPROXY',
    'TRACE',
    'TTL',
    'ULOG',
]

env = jinja2.Environment(
    loader=PackageLoader('dotiptables', 'templates'))

re_table = '''^\*(?P<table>\S+)'''
re_table = re.compile(re_table)

re_chain = '''^:(?P<chain>\S+) (?P<policy>\S+) (?P<counters>\S+)'''
re_chain = re.compile(re_chain)

re_rule = '''^(\[(?P<packets>\d+):(?P<bytes>\d+)\] )?-A (?P<chain>\S+)( (?P<conditions>.*))?( -(?:j|g) (?P<target>\S*))( (?P<extra>.*))?'''
re_rule = re.compile(re_rule)

re_commit = '''^COMMIT'''
re_commit = re.compile(re_commit)

re_comment = '''^#(?P<comment>.*)'''
re_comment = re.compile(re_comment)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--outputdir', '-d', default='./out')
    p.add_argument('--render', action='store_true', default="True")
    p.add_argument('input', nargs='?')

    return p.parse_args()


def stripped(fd):
    for line in fd:
        yield line.strip()


def handle_table(iptables, mo, line):
    iptables[mo.group('table')] = {}
    iptables['_table'] = iptables[mo.group('table')]


def handle_chain(iptables, mo, line):
    policy = mo.group('policy')
    if policy == '-':
        policy = None

    iptables['_table'][mo.group('chain')] = {
        'lines': [],
        'policy': policy,
        'rules': [],
        'targets': set(),
    }


def handle_rule(iptables, mo, line):
    fields = dict((k, v if v else '') for k, v in mo.groupdict().items())
    iptables['_table'][fields['chain']]['rules'].append(fields)
    iptables['_table'][fields['chain']]['lines'].append(line)

    if mo.group('target') and mo.group('target') in iptables['_table']:
        iptables['_table'][fields['chain']]['targets'].add(mo.group('target'))


def handle_commit(iptables, mo, line):
    iptables['_table'] = None


def read_chains(input):
    iptables = {
        '_table': None,
    }

    actions = (
        (re_table, handle_table),
        (re_chain, handle_chain),
        (re_rule, handle_rule),
        (re_commit, handle_commit),
        (re_comment, None),
    )

    for line in stripped(input):
        try:
            for pattern, action in actions:
                mo = pattern.match(line)
                if mo:
                    if action is not None:
                        action(iptables, mo, line)
                    raise StopIteration()
        except StopIteration:
            continue

        # We should never get here.
        print('unrecognized line:', line, file=sys.stderr)

    del iptables['_table']
    return iptables


def output_rules(iptables, opts):
    tmpl = env.get_template('rules.html')
    for table, chains in iptables.items():
        if table.startswith('_'):
            continue

        dir = os.path.join(opts.outputdir, table)
        try:
            os.mkdir(dir)
        except OSError as detail:
            if detail.errno == errno.EEXIST:
                pass
            else:
                raise

        for chain, data in chains.items():
            with open(os.path.join(dir, '%s.html' % chain), 'w') as fd:
                fd.write(tmpl.render(
                    table=table,
                    chain=chain,
                    builtin_targets=BUILTIN_TARGETS,
                    rules=data['rules'],
                    policy=data['policy']))


def output_dot_table(iptables, opts, table):
    tmpl = env.get_template('table.dot')

    with open(os.path.join(opts.outputdir, '%s.dot' % table), 'w') as fd:
        fd.write(tmpl.render(
            table=table,
            chains=iptables[table],
        ))
        fd.write('\n')


def output_dot(iptables, opts):
    tmpl = env.get_template('index.html')
    with open(os.path.join(opts.outputdir, 'index.html'), 'w') as fd:
        fd.write(tmpl.render(tables=iptables.keys()))

    for table in iptables:
        output_dot_table(iptables, opts, table)
        continue


def render_svg(iptables, opts):
    for table in iptables:
        p = subprocess.Popen(['dot', '-T', 'svg', '-o',
                              os.path.join(opts.outputdir, '%s.svg' % table),
                              os.path.join(opts.outputdir, '%s.dot' % table)])
        p.communicate()


def main():
    opts = parse_args()

    if not os.path.isdir(opts.outputdir):
        try:
            os.mkdir(opts.outputdir, 0o755)
            print('Output directory created: %s' % opts.outputdir)
        except:
            print((
                'ERROR: can''t created output directory: %s' % opts.outputdir
            ), file=sys.stderr)
            sys.exit(1)

    print('Reading iptables data.')
    with (open(opts.input, 'r') if opts.input else sys.stdin) as fd:
        iptables = read_chains(fd)

    print('Generating DOT output.')
    output_rules(iptables, opts)
    output_dot(iptables, opts)

    if opts.render:
        print('Generating SVG output.')
        render_svg(iptables, opts)


if __name__ == '__main__':
    main()
