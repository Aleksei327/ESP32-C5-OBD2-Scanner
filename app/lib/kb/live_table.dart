import 'knowledge_base.dart';

/// PSA-RE BSI live groups (C0–CF). Indexes and their order come from this ECU.
class LiveTable {
  LiveTable(this.groups);
  final Map<int, List<int>> groups;

  /// The table comes in pages. As the C3 II's BSI answers (21.11.2026):
  /// `75 C0 <80, or FF on the last page> 00 00 <page> <n> <n data bytes> <2 check bytes>`.
  /// The last page carries data too.
  static Future<LiveTable> read(Future<List<int>> Function(List<int>) ask) async {
    final bytes = <int>[];
    for (var page = 1; page <= 255; page++) {
      final reply = await ask([0x35, 0xc0, 0, 0, page, 0x11]);
      if (reply.length < 7 || reply[0] != 0x75 || reply[1] != 0xc0 || reply[5] != page) {
        throw const FormatException('Invalid BSI parameter table response');
      }
      final n = reply[6];
      if (reply.length < 7 + n) throw const FormatException('Short BSI parameter table page');
      bytes.addAll(reply.sublist(7, 7 + n));
      if (reply[2] == 0xff) return parse(bytes);
    }
    throw const FormatException('Incomplete BSI parameter table');
  }

  static LiveTable parse(List<int> bytes) {
    final groups = <int, List<int>>{};
    List<int>? current;
    for (final value in bytes) {
      if (value == 0xff) {
        current = null;
      } else if (current == null) {
        final lid = 0xc0 + value;
        if (value > 15 || groups.containsKey(lid)) {
          throw const FormatException('Invalid or duplicate BSI group');
        }
        current = groups[lid] = [];
      } else {
        if (current.contains(value)) throw const FormatException('Duplicate BSI parameter');
        current.add(value);
      }
    }
    return LiveTable(groups);
  }

  List<(Param, ParamValue)> decode(Record record, List<int> payload) {
    final definitions = record.m['indexed'] as Map;
    final params = <Param>[];
    var offset = 0;
    for (final index in groups[record.id] ?? const <int>[]) {
      final field = definitions['$index'] as Map<String, dynamic>?;
      if (field == null) throw FormatException('Unknown BSI parameter #$index');
      final width = field['width'] as int;
      if (width <= 0 || width > 8 && width % 8 != 0) {
        throw FormatException('Unsupported BSI field width $width');
      }
      if (width >= 8 || offset % 8 + width > 8) offset = (offset + 7) ~/ 8 * 8;
      final byte = offset ~/ 8 + 1;
      final low = offset % 8;
      final bits = width >= 8
          ? '$byte.7-${byte + width ~/ 8 - 1}.0'
          : '$byte.${low + width - 1}-$byte.$low';
      params.add(Param({...field, 'bits': bits}));
      offset += width;
    }
    if ((offset + 7) ~/ 8 != payload.length) {
      throw FormatException('BSI data length ${payload.length} does not match '
          'parameter table (${(offset + 7) ~/ 8})');
    }
    return [for (final p in params) (p, p.decode(payload))];
  }
}
