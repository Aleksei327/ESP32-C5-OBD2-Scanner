import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;

import 'bits.dart';

/// База знаний по машине: какие блоки стоят, их адреса и протоколы, модели блоков
/// (у одного места бывает несколько поставщиков), записи данных и тексты ошибок.
/// Собирается из PSA-RE скриптом tool/build_kb.py. Приложение марки в код не зашивает.
class KnowledgeBase {
  KnowledgeBase(this.data);
  final Map<String, dynamic> data;

  /// [extraDtc] — отдельный файл с текстами ошибок под другой лицензией (ludwig-v, GPL):
  /// не нашёлся — работаем без него.
  static Future<KnowledgeBase> load(String asset, {String? extraDtc}) async {
    final kb = KnowledgeBase(jsonDecode(await rootBundle.loadString(asset)) as Map<String, dynamic>);
    if (extraDtc != null) {
      try {
        kb.addDtcTexts(jsonDecode(await rootBundle.loadString(extraDtc)) as Map<String, dynamic>);
      } catch (_) {}
    }
    return kb;
  }

  /// Тексты ошибок из дополнительного файла: только те, которых у модели нет.
  void addDtcTexts(Map<String, dynamic> extra) {
    final byModel = extra['models'] as Map<String, dynamic>? ?? const {};
    for (final e in ecus) {
      for (final x in e.models) {
        final add = byModel[x.name] as Map?;
        if (add != null) x.extraDtc.addAll(add);
      }
    }
  }

  /// Общий текст кода SAE J2012 (P0130, U0100…) — когда у блока своего нет.
  String? genericDtc(String code, String lang) {
    final c = code.split('-').first;
    if (!isSaeCode(c)) return null;
    final t = (data['dtc_generic'] as Map?)?[c];
    return t == null ? null : txt(t, lang);
  }

  String get title => data['title'] as String? ?? '';
  String get diagBus => data['diag_bus'] as String? ?? 'B';
  String get obdBus => data['obd_bus'] as String? ?? 'A';
  int get bitrate => data['bitrate'] as int? ?? 500000;
  Map<String, dynamic> get source => data['source'] as Map<String, dynamic>? ?? const {};

  late final List<EcuDef> ecus = [for (final e in (data['ecus'] as List? ?? [])) EcuDef(e as Map<String, dynamic>)];
}

/// Код из диапазона, который определяет сам стандарт SAE J2012: P0, P2, P34–P39, B0, C0, U0.
/// В P1, B1/B2, C1/C2, U1/U2 и U3 коды у каждого производителя свои (PSA пишет туда
/// свои ошибки BSI), общий текст там был бы неверным.
bool isSaeCode(String c) {
  if (c.length != 5) return false;
  final d = c[1];
  return switch (c[0]) {
    'P' => d == '0' || d == '2' || (d == '3' && '456789'.contains(c[2])),
    'B' || 'C' || 'U' => d == '0',
    _ => false,
  };
}

/// Текст на языке интерфейса, иначе английский.
String txt(Object? m, String lang) {
  if (m is String) return m;
  if (m is Map) return (m[lang] ?? m['en'] ?? '') as String;
  return '';
}

List<int> unhex(String s) => [for (var i = 0; i + 1 < s.length; i += 2) int.parse(s.substring(i, i + 2), radix: 16)];

int _hexId(Object? v) => v is int ? v : int.parse(v.toString(), radix: 16);

/// Место блока в машине (BSI, двигатель, ABS…) — с адресом и возможными моделями.
class EcuDef {
  EcuDef(this.m);
  final Map<String, dynamic> m;

  String get node => m['node'] as String? ?? '?';
  String nameFor(String lang) => txt(m['name'], lang).isEmpty ? node : txt(m['name'], lang);
  int get tx => _hexId(m['tx']);
  int get rx => _hexId(m['rx']);
  bool get optional => m['optional'] as bool? ?? false;
  String? get icon => m['icon'] as String?;

  late final List<EcuModel> models = [for (final x in (m['models'] as List? ?? [])) EcuModel(x as Map<String, dynamic>)];

  /// Протоколы, на которых может говорить этот блок: сначала самый частый у моделей.
  List<String> get protos {
    final n = <String, int>{};
    for (final x in models) {
      for (final p in x.proto) {
        n[p] = (n[p] ?? 0) + (p == x.proto.first ? 2 : 1);
      }
    }
    return n.keys.toList()..sort((a, b) => n[b]!.compareTo(n[a]!));
  }

  /// Чем открывать сеанс KWP: варианты у разных моделей, самый частый первым.
  List<List<int>> get kwpOpens {
    final n = <String, int>{};
    for (final x in models) {
      if (x.open != null) n[x.open!] = (n[x.open!] ?? 0) + 1;
    }
    final keys = n.keys.toList()..sort((a, b) => n[b]!.compareTo(n[a]!));
    return [for (final k in keys) unhex(k)];
  }

  /// Текст ошибки, когда модель блока не опознана: ищем у всех моделей этого места.
  String? dtcText(String code, String lang) {
    for (final x in models) {
      final t = x.dtcText(code, lang);
      if (t != null) return t;
    }
    return null;
  }
}

/// Конкретная модель блока (например, двигатель Valeo V46): протокол, опознание, данные.
class EcuModel {
  EcuModel(this.m);
  final Map<String, dynamic> m;

  String get name => m['model'] as String? ?? '?';
  String titleFor(String lang) => txt(m['name'], lang).isEmpty ? name : txt(m['name'], lang);
  List<String> get proto => [for (final p in (m['proto'] as List? ?? const ['uds'])) p as String];
  String? get open => m['open'] as String?;
  List<int>? get identReq => m['ident']?['req'] == null ? null : unhex(m['ident']['req'] as String);
  Bits? get identPart => m['ident']?['part'] == null ? null : Bits.parse(m['ident']['part'] as String);

  /// Номер детали → вариант ПО (по нему выбираются нужные записи данных).
  String? variantOf(String part) => (m['parts'] as Map?)?[part] as String?;

  late final List<Record> records = [for (final r in (m['records'] as List? ?? [])) Record(r as Map<String, dynamic>)];

  /// Записи нужного вида для этого варианта ПО (вариант неизвестен — все).
  List<Record> recordsFor(String? variant, String kind) =>
      [for (final r in records) if (r.kind == kind && r.appliesTo(variant)) r];

  /// Тексты из дополнительного файла (KnowledgeBase.addDtcTexts).
  final Map<dynamic, dynamic> extraDtc = {};

  String? dtcText(String code, String lang) {
    final base = code.split('-').first;
    for (final d in [m['dtc'] as Map? ?? const {}, extraDtc]) {
      final t = d[code] ?? d[base];
      if (t != null) return txt(t, lang);
    }
    return null;
  }
}

bool matchVariant(List<String> patterns, String variant) => patterns.any(
    (p) => p.endsWith('*') ? variant.startsWith(p.substring(0, p.length - 1)) : variant == p);

/// Запись данных: запрос (21 LID для KWP, 22 DID для UDS) и значения в ответе.
class Record {
  Record(this.m);
  final Map<String, dynamic> m;

  late final List<int> req = unhex(m['req'] as String);
  String get kind => m['kind'] as String? ?? 'live';
  int? get len => m['len'] as int?;
  int get idLen => req.length - 1;

  /// Номер записи без кода сервиса: «C0» или «F190».
  String get label => (m['req'] as String).substring(2);
  int get id => int.parse(label, radix: 16);
  String nameFor(String lang) => txt(m['name'], lang);

  List<String> get _variants => [for (final v in (m['variants'] as List? ?? [])) v as String];

  bool appliesTo(String? variant) {
    if (variant == null || _variants.isEmpty || matchVariant(_variants, variant)) return true;
    return _alts.any((a) => a.$1.isEmpty || matchVariant(a.$1, variant));
  }

  late final List<Param> params = [for (final p in (m['params'] as List? ?? [])) Param(p as Map<String, dynamic>)];

  late final List<(List<String>, List<Param>)> _alts = [
    for (final a in (m['alts'] as List? ?? []))
      (
        [for (final v in (a['variants'] as List? ?? [])) v as String],
        [for (final p in (a['params'] as List? ?? [])) Param(p as Map<String, dynamic>)],
      )
  ];

  /// Раскладка значений для этого варианта ПО (у разных версий она бывает разной).
  List<Param> paramsFor(String? variant) {
    if (variant == null || _variants.isEmpty || matchVariant(_variants, variant)) return params;
    for (final (pats, ps) in _alts) {
      if (pats.isEmpty || matchVariant(pats, variant)) return ps;
    }
    return params;
  }

  /// Разобрать ответ блока (данные после номера записи).
  List<(Param, ParamValue)> decode(List<int> payload, String? variant) => [
        for (final p in paramsFor(variant))
          if (p.bits.fits(payload)) (p, p.decode(payload))
      ];
}

/// Значение параметра: число (для датчиков и графиков) и/или текст.
class ParamValue {
  const ParamValue({this.number, this.text, this.label});
  final double? number;
  final String? text;
  final Object? label; // {en, ru} из таблицы значений
}

class Param {
  Param(this.m);
  final Map<String, dynamic> m;

  String get key => m['key'] as String? ?? '';
  String nameFor(String lang) => txt(m['name'], lang).isEmpty ? key : txt(m['name'], lang);
  late final Bits bits = Bits.parse(m['bits'] as String);
  String get type => m['type'] as String? ?? 'uint';
  double get factor => (m['factor'] as num?)?.toDouble() ?? 1;
  double get offset => (m['offset'] as num?)?.toDouble() ?? 0;
  String get units => m['units'] as String? ?? '';
  bool get littleEndian => m['le'] as bool? ?? false;
  Map? get values => m['values'] as Map?;

  /// Сколько знаков после запятой показывать: по шагу величины.
  int get decimals {
    final f = factor.abs();
    if (f == 0 || f >= 1 && f == f.roundToDouble()) return 0;
    for (var d = 1; d < 4; d++) {
      final s = f * _pow10(d);
      if ((s - s.roundToDouble()).abs() < 1e-6) return d;
    }
    return 3;
  }

  static double _pow10(int d) => d == 1 ? 10 : d == 2 ? 100 : 1000;

  int _raw(List<int> p) {
    if (littleEndian) {
      final b = bits.bytes(p).reversed.toList();
      return b.fold(0, (v, x) => v * 256 + x);
    }
    return type == 'sint' ? bits.sint(p) : bits.uint(p);
  }

  ParamValue decode(List<int> p) {
    switch (type) {
      case 'str':
        return ParamValue(text: ascii(bits.bytes(p)));
      case 'bcd':
        return ParamValue(text: bcd(bits.bytes(p)));
      case 'bytes':
        return ParamValue(text: hexStr(bits.bytes(p)));
      case 'float':
        final f = float32(bits.bytes(p));
        return ParamValue(number: f * factor + offset);
    }
    final raw = _raw(p);
    final label = values?['$raw'];
    if (type == 'enum' || type == 'bool') {
      return ParamValue(number: raw.toDouble(), label: label, text: label == null ? '$raw' : null);
    }
    return ParamValue(number: raw * factor + offset, label: label);
  }
}
