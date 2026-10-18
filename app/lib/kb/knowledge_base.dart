import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;

/// База знаний по марке: адреса блоков, какие DID читать/писать, расшифровка ошибок.
/// Один JSON на платформу. Приложение не зашивает марки в код — читает отсюда.
class KnowledgeBase {
  KnowledgeBase(this.data);
  final Map<String, dynamic> data;

  static Future<KnowledgeBase> load(String asset) async {
    final txt = await rootBundle.loadString(asset);
    return KnowledgeBase(jsonDecode(txt) as Map<String, dynamic>);
  }

  String get title => data['title'] as String? ?? '';
  String get diagBus => data['diag_bus'] as String? ?? 'B';
  String get obdBus => data['obd_bus'] as String? ?? 'A';
  int get bitrate => data['bitrate'] as int? ?? 500000;

  List<EcuDef> get ecus =>
      [for (final e in (data['ecus'] as List? ?? [])) EcuDef(e as Map<String, dynamic>)];

  /// Описание параметра по номеру DID (для стоп-кадров), или null — неизвестен.
  LiveItem? did(int did) {
    final m = (data['dids'] as Map?)?['$did'];
    return m == null ? null : LiveItem({...(m as Map<String, dynamic>), 'did': did});
  }

  /// Текст ошибки на нужном языке, или null — тогда показываем голый код.
  String? dtcText(String code, String lang) {
    final m = (data['dtc'] as Map?)?[code] as Map?;
    return m?[lang] as String? ?? m?['en'] as String?;
  }
}

int _hexId(Object? v) => v is int ? v : int.parse(v.toString(), radix: 16);

class EcuDef {
  EcuDef(this.m);
  final Map<String, dynamic> m;

  String get name => m['name'] as String? ?? '?';
  String nameFor(String lang) =>
      (lang == 'en' ? m['name_en'] : null) as String? ?? name;
  int get tx => _hexId(m['tx']);
  int get rx => _hexId(m['rx']);
  String get proto => m['proto'] as String? ?? 'uds';
  int? get vinDid => m['idents']?['vin'] as int?;
  int? get partDid => m['idents']?['part'] as int?;
  int? get swDid => m['idents']?['sw'] as int?;

  List<ConfigItem> get config =>
      [for (final c in (m['config'] as List? ?? [])) ConfigItem(c as Map<String, dynamic>)];
  List<LiveItem> get live =>
      [for (final c in (m['live'] as List? ?? [])) LiveItem(c as Map<String, dynamic>)];
}

class ConfigItem {
  ConfigItem(this.m);
  final Map<String, dynamic> m;
  int get did => m['did'] as int;
  String nameFor(String lang) =>
      (lang == 'en' ? m['name_en'] : m['name_ru']) as String? ?? m['name_ru'] as String? ?? '?';
  String get type => m['type'] as String? ?? 'u8';
}

class LiveItem {
  LiveItem(this.m);
  final Map<String, dynamic> m;
  int get did => m['did'] as int;
  String nameFor(String lang) =>
      (lang == 'en' ? m['name_en'] : m['name_ru']) as String? ?? m['name_ru'] as String? ?? '?';
  String get unit => m['unit'] as String? ?? '';
  int get len => m['len'] as int? ?? 1;
  int get off => m['off'] as int? ?? 0;
  double get scale => (m['scale'] as num?)?.toDouble() ?? 1;
  int get decimals => m['decimals'] as int? ?? 0;
  bool get big => m['big'] as bool? ?? false;

  double value(List<int> b) {
    if (b.isEmpty) return 0;
    final raw = len >= 2 ? (b[0] << 8) | b[1] : b[0];
    return raw * scale + off;
  }
}
