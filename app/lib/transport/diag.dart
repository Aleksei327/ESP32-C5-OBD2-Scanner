import 'adapter_client.dart';

/// Протоколы диагностики блоков поверх ISO-TP: UDS (ISO 14229) и KWP2000 по-PSA
/// (сервисы ISO 14230-3 поверх того же ISO-TP). Для адаптера разницы нет — он просто
/// передаёт байты. Только чтение: сеанс, чтение записей, ошибки и их сброс.

class NegativeResponse implements Exception {
  NegativeResponse(this.sid, this.code);
  final int sid;
  final int code;
  @override
  String toString() => 'NRC 0x${code.toRadixString(16)} on SID 0x${sid.toRadixString(16)}';
}

class Dtc {
  Dtc(this.raw, this.status, {bool? active}) : active = active ?? (status & 0x01 != 0);

  /// 2 байта кода (KWP) или 3 (UDS: код + тип неисправности).
  final List<int> raw;
  final int status;
  final bool active;

  /// P0130, U0100… (первые два байта, SAE J2012).
  String get code {
    final b = raw[0];
    const letter = ['P', 'C', 'B', 'U'];
    final c = letter[(b >> 6) & 0x3];
    final d = ((b >> 4) & 0x3).toString();
    return '$c$d${(b & 0x0F).toRadixString(16)}${raw[1].toRadixString(16).padLeft(2, '0')}'.toUpperCase();
  }

  /// Код с типом неисправности (UDS): «B1003-00». По нему ищется текст в базе.
  String get key => raw.length >= 3 ? '$code-${raw[2].toRadixString(16).padLeft(2, '0').toUpperCase()}' : code;
}

abstract class DiagProtocol {
  DiagProtocol(this.client, this.bus, this.tx, this.rx);
  final AdapterClient client;
  final String bus;
  final int tx, rx;

  String get name;

  /// Запрос к блоку. Положительный ответ (сервис + 0x40) возвращается, отказ — исключение.
  Future<List<int>> ask(List<int> req, {int timeoutMs = 1500}) async {
    final r = await client.request(bus, tx, rx, req, timeoutMs: timeoutMs);
    if (r.isNotEmpty && r[0] == (req.first + 0x40) & 0xFF) return r;
    throw NegativeResponse(req.first, r.length > 2 && r[0] == 0x7F ? r[2] : 0x10);
  }

  /// Прочитать запись (21 LID или 22 DID): данные после эха номера записи.
  Future<List<int>> read(List<int> req) async => (await ask(req)).sublist(req.length);

  Future<List<Dtc>> readDtcs();
  Future<void> clearDtcs();
}

class Uds extends DiagProtocol {
  Uds(super.client, super.bus, super.tx, super.rx);

  @override
  String get name => 'UDS';

  Future<void> session(int type) => ask([0x10, type]);

  Future<List<int>> readDid(int did) => read([0x22, did >> 8, did & 0xFF]);

  Future<String> readDidAscii(int did) async {
    final b = await readDid(did);
    return String.fromCharCodes(b.where((c) => c >= 0x20 && c < 0x7F)).trim();
  }

  @override
  Future<List<Dtc>> readDtcs() async {
    final r = await ask([0x19, 0x02, 0xFF]);
    final body = r.sublist(3);
    return [for (var i = 0; i + 4 <= body.length; i += 4) Dtc(body.sublist(i, i + 3), body[i + 3])];
  }

  /// Стоп-кадр ошибки (19 04): пары DID → байты. Длину значения каждого DID
  /// знает только база знаний, поэтому её передаём снаружи ([lenOf], null — не знаем).
  Future<List<(int, List<int>)>> readSnapshot(List<int> dtc, int? Function(int did) lenOf) async {
    final r = await ask([0x19, 0x04, dtc[0], dtc[1], dtc.length > 2 ? dtc[2] : 0, 0xFF]);
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

  @override
  Future<void> clearDtcs() => ask([0x14, 0xFF, 0xFF, 0xFF]);
}

/// KWP2000 по-PSA на CAN (PSA-RE: diag/protocols/KWP-PSA2000.yml).
/// Сеанс: 81 у блоков шины IS (двигатель, ABS…), 10 C0 у блоков салона через BSI;
/// держится запросами не реже раза в несколько секунд.
class Kwp extends DiagProtocol {
  Kwp(super.client, super.bus, super.tx, super.rx);

  @override
  String get name => 'KWP2000';

  Future<void> open(List<int> req, {int timeoutMs = 1500}) => ask(req, timeoutMs: timeoutMs);

  Future<List<int>> readLid(int lid) => read([0x21, lid]);

  /// 17 FF 00 → 57 <число> {код(2) состояние}...
  /// Состояние по ISO 14230-3: биты 6–5 = 11 — неисправность есть сейчас,
  /// 01 — сохранена. Как именно ставят биты блоки PSA, проверить на машине.
  @override
  Future<List<Dtc>> readDtcs() async {
    final r = await ask([0x17, 0xFF, 0x00]);
    final out = <Dtc>[];
    for (var i = 2; i + 3 <= r.length; i += 3) {
      final st = r[i + 2];
      out.add(Dtc(r.sublist(i, i + 2), st, active: (st >> 5) & 0x3 == 0x3));
    }
    return out;
  }

  @override
  Future<void> clearDtcs() => ask([0x14, 0xFF, 0x00]);
}
