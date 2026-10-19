import '../kb/knowledge_base.dart';
import '../transport/adapter_client.dart';
import '../transport/diag.dart';
import '../transport/obd.dart';

/// Ход поиска блоков: сколько адресов проверено и кто откликнулся (запрос, ответ).
class DiscoveryStep {
  DiscoveryStep(this.done, this.total, this.found);
  final int done, total;
  final List<(int, int)> found;
}

/// Связь с одним блоком в этом подключении: на каком протоколе он ответил,
/// какая это модель (по номеру детали) и какой вариант ПО.
class EcuLink {
  EcuLink(this.def);
  final EcuDef def;

  bool answered = false;
  DiagProtocol? proto;
  List<int>? kwpOpen; // каким запросом открылся сеанс KWP
  DateTime _last = DateTime.fromMillisecondsSinceEpoch(0);

  EcuModel? model;
  bool modelChosen = false; // выбрана руками, а не опознана
  String? part;
  String? variant;
  List<Dtc> dtcs = [];

  String get name => def.node;
}

/// Итог опроса одного блока при автоскане.
typedef EcuResult = EcuLink;

/// Сведения о блоке для вкладки «Инфо».
class EcuInfo {
  EcuInfo(this.link, this.vin, this.rows);
  final EcuLink link;
  final String? vin;
  final List<(Param, ParamValue)> rows;
}

/// Диагностика поверх транспорта и базы знаний: автоскан, опознание блоков, ошибки,
/// записи данных. Всё, что «умно», живёт тут, не в адаптере. Только чтение.
class DiagService {
  DiagService(this.client, this.kb);
  final AdapterClient client;
  final KnowledgeBase kb;

  final _links = <int, EcuLink>{};

  /// Сколько ждать блок при опросе «ты здесь?». Живые отвечают за десятки мс.
  static const probeTimeoutMs = 300;

  /// Сеанс KWP без запросов гаснет через несколько секунд: переоткрываем заранее.
  static const kwpIdle = Duration(seconds: 2);

  EcuLink link(EcuDef d) => _links.putIfAbsent(d.tx, () => EcuLink(d));

  Future<void> openDiag({bool write = false}) => client.openBus(kb.diagBus, listen: !write, bitrate: kb.bitrate);

  /// Пройти по всем блокам: ответил ли, какая модель, сколько ошибок. Один блок за раз.
  /// Опрос — это запросы, значит шину открываем на передачу (не listen-only).
  Stream<EcuResult> autoScan() async* {
    await openDiag(write: true);
    for (final def in kb.ecus) {
      final l = link(def);
      l.dtcs = [];
      try {
        l.answered = await _probe(l);
        if (l.answered) {
          await detectModel(l);
          try {
            l.dtcs = await readFaults(def);
          } on NegativeResponse {
            l.dtcs = [];
          }
        }
      } catch (_) {
        // блок ответил, а дальше связь пропала — считаем по тому, что успели
      }
      yield l;
    }
  }

  /// Есть ли блок и на каком протоколе он говорит. KWP пробуем сеансом (81 или 10 C0),
  /// UDS — «я здесь» (3E 00). Ответ отказом — тоже ответ: блок на месте.
  Future<bool> _probe(EcuLink l) async {
    final d = l.def;
    var alive = false;
    for (final p in d.protos) {
      if (p == 'kwp') {
        final kwp = Kwp(client, kb.diagBus, d.tx, d.rx);
        for (final open in d.kwpOpens) {
          try {
            await kwp.open(open, timeoutMs: probeTimeoutMs);
            l.proto = kwp;
            l.kwpOpen = open;
            l._last = DateTime.now();
            return true;
          } on NegativeResponse {
            alive = true;
          } on AdapterError {
            if (!alive) break; // молчит — других сеансов не пробуем
          }
        }
      } else {
        final uds = Uds(client, kb.diagBus, d.tx, d.rx);
        try {
          await uds.ask(const [0x3E, 0x00], timeoutMs: probeTimeoutMs);
          l.proto = uds;
          return true;
        } on NegativeResponse {
          l.proto ??= uds;
          return true;
        } on AdapterError {
          // нет ответа
        }
      }
    }
    if (alive) {
      l.proto ??= Kwp(client, kb.diagBus, d.tx, d.rx);
    }
    return alive;
  }

  DiagProtocol _proto(EcuLink l) =>
      l.proto ??
      (l.def.protos.first == 'kwp'
          ? Kwp(client, kb.diagBus, l.def.tx, l.def.rx)
          : Uds(client, kb.diagBus, l.def.tx, l.def.rx));

  /// Перед запросом: держим сеанс KWP открытым (переоткрываем после простоя).
  Future<DiagProtocol> _ready(EcuLink l) async {
    final p = _proto(l);
    if (p is Kwp && l.kwpOpen != null && DateTime.now().difference(l._last) > kwpIdle) {
      try {
        await p.open(l.kwpOpen!);
      } catch (_) {}
    }
    l._last = DateTime.now();
    return p;
  }

  Future<T> _run<T>(EcuLink l, Future<T> Function(DiagProtocol p) f) async {
    final p = await _ready(l);
    try {
      return await f(p);
    } finally {
      l._last = DateTime.now();
    }
  }

  /// Какая это модель: читаем номер детали командой опознания и ищем его у моделей.
  /// Не нашли, а модель у места одна — берём её. Иначе модель выберет пользователь.
  Future<void> detectModel(EcuLink l) async {
    if (l.model != null) return;
    final cands = [
      for (final m in l.def.models)
        if (l.proto == null || m.proto.contains(l.proto is Kwp ? 'kwp' : 'uds')) m
    ];
    final asked = <String, List<int>?>{};
    for (final m in cands) {
      final req = m.identReq, bits = m.identPart;
      if (req == null || bits == null) continue;
      final k = req.join(',');
      if (!asked.containsKey(k)) {
        try {
          asked[k] = await _run(l, (p) => p.read(req));
        } catch (_) {
          asked[k] = null;
        }
      }
      final payload = asked[k];
      if (payload == null || !bits.fits(payload)) continue;
      final part = Param({'bits': m.m['ident']['part'], 'type': 'bcd'}).decode(payload).text!;
      l.part ??= part;
      final v = m.variantOf(part);
      if (v != null) {
        l.model = m;
        l.part = part;
        l.variant = v;
        return;
      }
    }
    if (cands.length == 1) {
      l.model = cands.first;
    } else if (l.def.models.length == 1) {
      l.model = l.def.models.first;
    }
  }

  /// Пользователь сам указал модель блока (опознать не вышло).
  void chooseModel(EcuDef d, EcuModel m) {
    final l = link(d);
    l.model = m;
    l.modelChosen = true;
    l.variant = null;
  }

  /// Модели, из которых можно выбрать (подходят по протоколу).
  List<EcuModel> modelChoices(EcuDef d) {
    final l = link(d);
    final kind = l.proto is Kwp ? 'kwp' : l.proto is Uds ? 'uds' : null;
    return [for (final m in d.models) if (kind == null || m.proto.contains(kind)) m];
  }

  /// Записи нужного вида для опознанной (или выбранной) модели.
  List<Record> records(EcuDef d, String kind) {
    final l = link(d);
    return l.model?.recordsFor(l.variant, kind) ?? const [];
  }

  Future<List<(Param, ParamValue)>> readRecord(EcuDef d, Record r) async {
    final l = link(d);
    final payload = await _run(l, (p) => p.read(r.req));
    return r.decode(payload, l.variant);
  }

  /// Модель, номер детали, VIN и записи опознания.
  Future<EcuInfo> identify(EcuDef d) async {
    final l = link(d);
    if (l.proto == null) await _probe(l);
    await detectModel(l);
    final rows = <(Param, ParamValue)>[];
    String? vin;
    for (final r in records(d, 'identification')) {
      try {
        rows.addAll(await readRecord(d, r));
      } catch (_) {}
    }
    // VIN: запись с параметром VIN (у BSI это настройка B0), у UDS — ещё и F190
    final withVin = [
      for (final kind in const ['identification', 'config'])
        for (final r in records(d, kind))
          if (r.paramsFor(l.variant).any((p) => p.key == 'VIN')) r
    ];
    for (final r in withVin) {
      try {
        final v = (await readRecord(d, r)).where((e) => e.$1.key == 'VIN').firstOrNull;
        if (v?.$2.text?.isNotEmpty ?? false) {
          vin = v!.$2.text;
          break;
        }
      } catch (_) {}
    }
    if (vin == null && l.proto is Uds) {
      try {
        vin = await (l.proto as Uds).readDidAscii(0xF190);
      } catch (_) {}
    }
    for (final (p, v) in rows) {
      if (vin == null && p.key == 'VIN' && (v.text?.isNotEmpty ?? false)) vin = v.text;
    }
    return EcuInfo(l, vin, rows);
  }

  /// VIN машины: у блоков (BSI, двигатель), иначе по OBD-II (режим 09).
  Future<String?> carVin(List<EcuLink> answered) async {
    for (final l in answered) {
      try {
        final i = await identify(l.def);
        if (i.vin != null && i.vin!.length >= 11) return i.vin;
      } catch (_) {}
    }
    try {
      await client.openBus(kb.obdBus, listen: false);
      final v = await Obd(client).vin();
      if (v.length >= 11) return v;
    } catch (_) {}
    return null;
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

  Future<List<Dtc>> readFaults(EcuDef d) => _run(link(d), (p) => p.readDtcs());
  Future<void> clearFaults(EcuDef d) => _run(link(d), (p) => p.clearDtcs());

  /// Текст ошибки: из опознанной модели, иначе из любой модели этого места,
  /// иначе общий текст кода SAE (generic — в интерфейсе это помечается).
  ({String text, bool generic})? dtcInfo(EcuDef d, Dtc dtc, String lang) {
    final m = link(d).model;
    final own = m?.dtcText(dtc.key, lang) ?? d.dtcText(dtc.key, lang);
    if (own != null) return (text: own, generic: false);
    final g = kb.genericDtc(dtc.code, lang);
    return g == null ? null : (text: g, generic: true);
  }

  String? dtcText(EcuDef d, Dtc dtc, String lang) => dtcInfo(d, dtc, lang)?.text;

  /// Стоп-кадр: какие были условия, когда ошибка появилась. Есть только у UDS
  /// (19 04); KWP-блоки PSA его так не отдают — тогда пусто.
  Future<List<(Param, ParamValue)>> readSnapshot(EcuDef d, Dtc dtc) async {
    final l = link(d);
    if (l.proto is! Uds || l.model == null) return const [];
    final byDid = {
      for (final r in l.model!.records)
        if (r.req.first == 0x22 && r.len != null) r.id: r
    };
    final raw = await _run(l, (p) => (p as Uds).readSnapshot(dtc.raw, (did) => byDid[did]?.len));
    return [
      for (final (did, bytes) in raw)
        if (byDid[did] case final r?) ...r.decode(bytes, l.variant)
    ];
  }
}
