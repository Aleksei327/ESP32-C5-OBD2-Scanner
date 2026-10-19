"""Русский текст для общих кодов SAE J2012 по частям.

Тексты SAE построены по шаблону: «узел [буква/номер] вид-неисправности [ряд/датчик]»,
например «Exhaust Pressure Sensor A Circuit Low Bank 2». Узлы и виды неисправностей
переводятся по отдельности (tool/kb_ru.json: sae_parts / sae_faults), фраза собирается:
«Датчик давления выхлопа A: низкий уровень сигнала в цепи, ряд 2».
Что не разбирается по шаблону — переводится целиком, как остальные строки базы.
"""
import re

QUAL = re.compile(r' (Bank (\d+)(?: Sensor (\d+))?|Sensor (\d+))$')
PREFIXES = [   # «Lost Communication With X» — X переводится как узел
    ('Lost Communication With ', 'Нет связи: {}'),
    ('Invalid Data Received From ', 'Недостоверные данные от: {}'),
    ('Implausible Data Received From ', 'Неправдоподобные данные от: {}'),
]


def split(text, faults):
    """(узел, метка, вид неисправности, ряд, датчик) или None, если не по шаблону."""
    qual_bank = qual_sensor = None
    m = QUAL.search(text)
    if m:
        qual_bank, qual_sensor = m.group(2), m.group(3) or m.group(4)
        text = text[:m.start()]
    fault = None
    for f in faults:                       # самый длинный вид неисправности, что подходит
        if text.endswith(' ' + f):
            fault = f
            text = text[:-len(f) - 1]
            break
    tag = None
    m = re.fullmatch(r'(.+?) ([A-J]|\d{1,2})', text)
    if m:
        text, tag = m.group(1), m.group(2)
    if fault is None and qual_bank is None and qual_sensor is None and tag is None:
        return None
    return text, tag, fault, qual_bank, qual_sensor


def compose(text, parts, faults):
    """Русский текст или None, если чего-то нет в словаре."""
    for pre, tpl in PREFIXES:
        if text.startswith(pre):
            rest = text[len(pre):]
            ru = parts.get(rest) or compose_part(rest, parts)
            if ru and len(ru) > 1 and ru[1].islower():   # «Блок …» → «блок …», ABS не трогаем
                ru = ru[0].lower() + ru[1:]
            return tpl.format(ru) if ru else None
    s = split(text, sorted(faults, key=len, reverse=True))
    if s is None:
        return None
    stem, tag, fault, bank, sensor = s
    ru_stem = parts.get(stem)
    if ru_stem is None:
        return None
    out = ru_stem + (f' {tag}' if tag else '')
    if fault:
        out += f': {faults[fault]}'
    q = []
    if bank:
        q.append(f'ряд {bank}')
    if sensor:
        q.append(f'датчик {sensor}')
    if q:
        out += ', ' + ', '.join(q)
    return out


def compose_part(text, parts):
    m = re.fullmatch(r'(.+?) ([A-J]|\d{1,2}|"[A-Z]")', text)
    if m and m.group(1) in parts:
        return f'{parts[m.group(1)]} {m.group(2)}'
    return None
