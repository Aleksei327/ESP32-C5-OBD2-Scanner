import '../kb/knowledge_base.dart';
import '../transport/adapter_client.dart';
import '../transport/uds.dart';

/// Ход поиска блоков: сколько адресов проверено и кто откликнулся (запрос, ответ).
class DiscoveryStep {
  DiscoveryStep(this.done, this.total, this.found);
  final int done, total;
  final List<(int, int)> found;
}

/// Итог опроса одного блока при автоскане.
class EcuResult {
  EcuResult(this.def);
  final EcuDef def;
  bool answered = false;
  List<Dtc> dtcs = [];
  String get name => def.name;
}

/// Диагностика поверх транспорта и базы знаний: автоскан, ошибки, настройки (чтение),
/// живые данные. Всё, что «умно», живёт тут, не в адаптере.
class DiagService {
  DiagService(this.client, this.kb);
  final AdapterClient client;
  final KnowledgeBase kb;

  Uds _uds(EcuDef e) => Uds(client, kb.diagBus, e.tx, e.rx);

  Future<void> openDiag({bool write = false}) =>
      client.openBus(kb.diagBus, listen: !write, bitrate: kb.bitrate);

  /// Пройти по всем блокам: ответил ли, сколько ошибок. Один блок за раз.
  /// Опрос — это запросы, значит шину открываем на передачу (не listen-only).
  Stream<EcuResult> autoScan() async* {
    await openDiag(write: true);
    for (final def in kb.ecus) {
      final r = EcuResult(def);
      try {
        final u = _uds(def);
        if (def.vinDid != null) {
          await u.readDid(def.vinDid!); // «ты живой?»
        }
        r.answered = true;
        try {
          r.dtcs = await u.readDtcs();
        } on NegativeResponse {
          r.dtcs = [];
        }
      } on AdapterError {
        r.answered = false;
      } on NegativeResponse {
        r.answered = true; // ответил отказом — значит на связи
      } catch (_) {
        r.answered = false;
      }
      yield r;
    }
  }

  Future<Map<String, String>> identify(EcuDef e) async {
    final u = _uds(e);
    final out = <String, String>{};
    Future<void> grab(String k, int? did) async {
      if (did == null) return;
      try {
        out[k] = await u.readDidAscii(did);
      } catch (_) {}
    }

    await grab('vin', e.vinDid);
    await grab('part', e.partDid);
    await grab('sw', e.swDid);
    return out;
  }

  /// Поиск блоков: перебираем адреса запросов, спрашиваем «я здесь» (3E 00).
  /// Ответил чем угодно, даже отказом, — на этом адресе есть блок.
  /// Адрес ответа не угадываем (у PSA бывает 752→652 и 6A8→688): адаптер
  /// сам сообщает, откуда пришёл ответ. Отдаёт ход и находки (запрос, ответ).
  Stream<DiscoveryStep> discover({int from = 0x600, int to = 0x7DF, int timeoutMs = 60}) async* {
    await openDiag(write: true);
    final found = <(int, int)>[];
    for (var tx = from; tx <= to; tx++) {
      try {
        final (rx, r) = await client.requestAnyRx(kb.diagBus, tx, const [0x3E, 0x00], timeoutMs: timeoutMs);
        if (r.isNotEmpty) found.add((tx, rx));
      } catch (_) {}
      if (tx % 8 == 0 || tx == to) yield DiscoveryStep(tx - from + 1, to - from + 1, List.of(found));
    }
  }

  Future<List<Dtc>> readFaults(EcuDef e) => _uds(e).readDtcs();
  Future<void> clearFaults(EcuDef e) => _uds(e).clearDtcs();

  /// Стоп-кадр: какие были условия, когда ошибка появилась.
  Future<List<(LiveItem, double)>> readSnapshot(EcuDef e, Dtc d) async {
    final raw = await _uds(e).readSnapshot(d.raw, (did) => kb.did(did)?.len);
    return [
      for (final (did, bytes) in raw)
        if (kb.did(did) case final item?) (item, item.value(bytes)),
    ];
  }

  Future<Map<int, int>> readConfig(EcuDef e) async {
    final u = _uds(e);
    await u.session(3);
    final out = <int, int>{};
    for (final c in e.config) {
      try {
        final b = await u.readDid(c.did);
        if (b.isNotEmpty) out[c.did] = b.first;
      } catch (_) {}
    }
    return out;
  }

  Future<List<double>> readLive(EcuDef e) async {
    final u = _uds(e);
    final out = <double>[];
    for (final item in e.live) {
      try {
        out.add(item.value(await u.readDid(item.did)));
      } catch (_) {
        out.add(double.nan);
      }
    }
    return out;
  }

}
