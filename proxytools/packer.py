#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Unpacker for Dean Edward's p.a.c.k.e.r, a part of javascript beautifier
# by Einar Lielmanis <einar@jsbeautifier.org>
#
#     written by Stefano Sanfilippo <a.little.coder@gmail.com>
#
# usage:
#
# if detect(some_string):
#     unpacked = unpack(some_string)
#
# 2018-04-11: UPDATE by neskk
# Merged changes from: https://github.com/beautify-web/js-beautify/pull/1368
# Made various small cosmetic tweaks.
# 2020-05-10: Python 3 adjustments
#
"""Unpacker for Dean Edward's p.a.c.k.e.r"""

import re


class UnpackingError(Exception):
    """Badly packed source or general error. Argument is a
    meaningful description."""
    pass


def deobfuscate(source):
    """Detects whether `source` is obfuscated coded."""
    source = source.replace(' ', '')

    if source.startswith('eval(function(p,r,o,x,y,s)'):
        converted = convert_proxys(source)
        return unpack(converted)

    if source.startswith('eval(function(p,a,c,k,e,'):
        return unpack(source)

    return False


def convert_proxys(source):
    """Convert P.R.O.X.Y.S. to P.A.C.K.E.R."""
    pieces = source.split("'")
    if len(pieces) < 4:
        raise UnpackingError('Unknown p.r.o.x.y.s. encoding.')

    if pieces[-3] != '.split(':
        raise UnpackingError('Unknown p.r.o.x.y.s. encoding.')

    # Find custom separator
    separator = pieces[-2].encode().decode('unicode_escape')

    # Replace with standard P.A.C.K.E.R. separator
    pieces[-2] = '|'
    pieces[-4] = pieces[-4].replace(separator, '|')

    return "'".join(pieces)


def unpack(source):
    """Unpacks P.A.C.K.E.R. packed js code."""
    payload, symtab, radix, count = _filterargs(source)

    if count != len(symtab):
        raise UnpackingError('Malformed p.a.c.k.e.r. symtab.')

    try:
        unbase = Unbaser(radix)
    except TypeError:
        raise UnpackingError('Unknown p.a.c.k.e.r. encoding.')

    def lookup(match):
        """Look up symbols in the synthetic symtab."""
        word = match.group(0)
        return symtab[unbase(word)] or word

    source = re.sub(r'\b\w+\b', lookup, payload)
    return _replacestrings(source)


def _filterargs(source):
    """Juice from a source file the four args needed by decoder."""
    juicers = [(r"}\('(.*)', *(\d+), *(\d+), *'(.*)'\.split\('\|'\), *(\d+), *(.*)\)\)"), # noqa501
               (r"}\('(.*)', *(\d+), *(\d+), *'(.*)'\.split\('\|'\)")]

    for juicer in juicers:
        args = re.search(juicer, source, re.DOTALL)
        if args:
            a = args.groups()
            try:
                return a[0], a[3].split('|'), int(a[1]), int(a[2])
            except ValueError:
                raise UnpackingError('Corrupted p.a.c.k.e.r. data.')

    # could not find a satisfying regex
    raise UnpackingError('Could not make sense of p.a.c.k.e.r data '
                         '(unexpected code structure).')


def _replacestrings(source):
    """Strip string lookup table (list) and replace values in source."""
    match = re.search(r'var *(_\w+)\=\["(.*?)"\];', source, re.DOTALL)

    if match:
        varname, strings = match.groups()
        startpoint = len(match.group(0))
        lookup = strings.split('","')
        variable = '%s[%%d]' % varname
        for index, value in enumerate(lookup):
            source = source.replace(variable % index, '"%s"' % value)
        return source[startpoint:]
    return source


class Unbaser(object):
    """Functor for a given base. Will efficiently convert
    strings to natural numbers."""
    ALPHABET = {
        62: '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
        95: (' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ'
             '[\]^_`abcdefghijklmnopqrstuvwxyz{|}~')
    }

    def __init__(self, base):
        self.base = base

        # fill elements 37...61, if necessary
        if 36 < base < 62:
            if not hasattr(self.ALPHABET, self.ALPHABET[62][:base]):
                self.ALPHABET[base] = self.ALPHABET[62][:base]
            # attrs = self.ALPHABET
            # print ', '.join("%s: %s" % item for item in attrs.items())

        # If base can be handled by int() builtin, let it do it for us
        if 2 <= base <= 36:
            self.unbase = lambda string: int(string, base)
        else:
            # Build conversion dictionary cache
            try:
                self.dictionary = dict(
                    (cipher, index) for index, cipher in
                    enumerate(self.ALPHABET[base]))
            except KeyError:
                raise TypeError('Unsupported base encoding.')

            self.unbase = self._dictunbaser

    def __call__(self, string):
        return self.unbase(string)

    def _dictunbaser(self, string):
        """Decodes a  value to an integer."""
        ret = 0
        for index, cipher in enumerate(string[::-1]):
            ret += (self.base ** index) * self.dictionary[cipher]
        return ret
