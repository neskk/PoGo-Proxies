#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Crazy XOR deobfuscator.
#
# Builds a dictionary with the decoding information.
# decoder_dict = {'<var>': <value>, ...}.
#


def parse_crazyxor(code):
    dictionary = {}
    variables = code.split(';')
    for var in variables:
        if '=' in var:
            assignment = var.split('=')
            var = assignment[0].strip()
            value = assignment[1].strip()
            dictionary[var] = value

    for var in dictionary:
        recursive_decode(dictionary, var)
    return dictionary


def recursive_decode(dictionary, var):
    if var.isdigit():
        return var

    value = dictionary[var]
    if value.isdigit():
        return value
    elif '^' in value:
        l_value, r_value = value.split('^')
        answer = str(int(recursive_decode(dictionary, l_value)) ^
                     int(recursive_decode(dictionary, r_value)))
        dictionary[var] = answer
        return answer


def decode_crazyxor(dictionary, code):
    if code.isdigit():
        return code
    value = dictionary.get(code, False)
    if value and value.isdigit():
        return value
    elif '^' in code:
        l_value, r_value = code.split('^', 1)
        answer = str(int(decode_crazyxor(dictionary, l_value)) ^
                     int(decode_crazyxor(dictionary, r_value)))
        return answer
