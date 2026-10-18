import 'adapter_client.dart';

/// Поверх транспорта: UDS (ISO 14229) и чуть-чуть OBD-II.
/// Только чтение: сессия, чтение по DID, ошибки и их сброс.

class NegativeResponse implements Exception {
  NegativeResponse(this.sid, this.code);
  final int sid;
  final int code;
  @override
  String toString() => 'NRC 0x${code.toRadixString(16)} on SID 0x${sid.toRadixString(16)}';
}

class Dtc {
  Dtc(this.raw, this.status);
  final List<int> raw;
  final int status;
  bool get active => status & 0x01 != 0;

  String get code {
    final b = raw[0];
    const letter = ['P', 'C', 'B', 'U'];
    final c = letter[(b >> 6) & 0x3];
    final d = ((b >> 4) & 0x3).toString();
    return '$c$d${(b & 0x0F).toRadixString(16)}${raw[1].toRadixString(16).padLeft(2, '0')}'
        .toUpperCase();
  }
}

class Uds {
  Uds(this.client, this.bus, this.tx, this.rx);
  final AdapterClient client;
  final String bus;
  final int tx, rx;

  /// Запрос к блоку. Положительный ответ возвращается, отказ — исключение.
  Future<List<int>> ask(List<int> req, int okByte) async {
    final r = await client.request(bus, tx, rx, req);
    if (r.isNotEmpty && r[0] == okByte) return r;
    final code = r.length > 2 ? r[2] : 0x10;
    throw NegativeResponse(req.first, code);
  }

  Future<void> session(int type) => ask([0x10, type], 0x50);

  Future<List<int>> readDid(int did) async {
    final r = await ask([0x22, did >> 8, did & 0xFF], 0x62);
    return r.sublist(3);
  }

  Future<String> readDidAscii(int did) async {
    final b = await readDid(did);
    return String.fromCharCodes(b.where((c) => c >= 0x20 && c < 0x7F)).trim();
  }

  Future<List<Dtc>> readDtcs() async {
    final r = await ask([0x19, 0x02, 0xFF], 0x59);
    final body = r.sublist(3);
    final out = <Dtc>[];
    for (var i = 0; i + 4 <= body.length; i += 4) {
      out.add(Dtc(body.sublist(i, i + 3), body[i + 3]));
    }
    return out;
  }

  /// Стоп-кадр ошибки (19 04): пары DID → байты. Длину значения каждого DID
  /// знает только база знаний, поэтому её передаём снаружи ([lenOf], null — не знаем).
  Future<List<(int, List<int>)>> readSnapshot(List<int> dtc, int? Function(int did) lenOf) async {
    final r = await ask([0x19, 0x04, dtc[0], dtc[1], dtc[2], 0xFF], 0x59);
    final out = <(int, List<int>)>[];
    // 59 04 <DTC 3> <статус> <номер записи> <число DID> {DID(2) данные}...
    if (r.length < 8) return out;
    final count = r[7];
    var i = 8;
    for (var n = 0; n < count && i + 2 <= r.length; n++) {
      final did = (r[i] << 8) | r[i + 1];
      final len = lenOf(did);
      if (len == null || i + 2 + len > r.length) break; // дальше не разобрать
      out.add((did, r.sublist(i + 2, i + 2 + len)));
      i += 2 + len;
    }
    return out;
  }

  Future<void> clearDtcs() => ask([0x14, 0xFF, 0xFF, 0xFF], 0x54);
}

/// OBD-II на шине A (7DF -> 7E8): только чтение.
class Obd {
  Obd(this.client);
  final AdapterClient client;

  Future<List<int>> _pid(int mode, int pid, int okByte) async {
    final r = await client.request('A', 0x7DF, 0x7E8, [mode, pid]);
    if (r.isNotEmpty && r[0] == okByte) return r;
    throw NegativeResponse(mode, r.length > 2 ? r[2] : 0x10);
  }

  Future<int> rpm() async {
    final r = await _pid(0x01, 0x0C, 0x41);
    return ((r[2] << 8) | r[3]) ~/ 4;
  }

  Future<int> coolant() async {
    final r = await _pid(0x01, 0x05, 0x41);
    return r[2] - 40;
  }

  /// Байты значения любого параметра режима 01 (без заголовка `41 pid`).
  Future<List<int>> pid(int pid) async => (await _pid(0x01, pid, 0x41)).sublist(2);

  /// Какие параметры режима 01 машина поддерживает (по маскам 00/20/40/60).
  Future<Set<int>> supportedPids() async {
    final out = <int>{};
    for (var base = 0x00; base <= 0x60; base += 0x20) {
      final List<int> m;
      try {
        m = await pid(base);
      } catch (_) {
        break;
      }
      final bits = (m[0] << 24) | (m[1] << 16) | (m[2] << 8) | m[3];
      for (var i = 1; i <= 32; i++) {
        if (bits & (1 << (32 - i)) != 0) out.add(base + i);
      }
      if (!out.contains(base + 0x20)) break;
    }
    return out;
  }

  Future<String> vin() async {
    final r = await _pid(0x09, 0x02, 0x49);
    return String.fromCharCodes(r.sublist(3).where((c) => c >= 0x20 && c < 0x7F));
  }
}
