"""Minimal KiCad S-expression parser / writer."""
import re

TOK = re.compile(r'\s*(\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+)')


def parse(text):
    stack = [[]]
    for m in TOK.finditer(text):
        t = m.group(1)
        if t == '(':
            stack.append([])
        elif t == ')':
            x = stack.pop()
            stack[-1].append(x)
        else:
            stack[-1].append(t)
    return stack[0]


def unq(s):
    if isinstance(s, str) and s.startswith('"'):
        return s[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    return s


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def dump(x, ind=0):
    if not isinstance(x, list):
        return x
    if not x:
        return '()'
    head = []
    for i in x:
        if isinstance(i, list):
            break
        head.append(i)
    rest = x[len(head):]
    if not rest:
        return '(' + ' '.join(head) + ')'
    s = '(' + ' '.join(head)
    for r in rest:
        s += '\n' + '\t' * (ind + 1) + dump(r, ind + 1)
    return s + '\n' + '\t' * ind + ')'


def find(lst, key):
    return [i for i in lst if isinstance(i, list) and i and i[0] == key]


def get(lst, key):
    r = find(lst, key)
    return r[0] if r else None


def load_lib(path):
    with open(path, encoding='utf-8') as f:
        root = parse(f.read())[0]
    return {unq(s[1]): s for s in find(root, 'symbol')}
