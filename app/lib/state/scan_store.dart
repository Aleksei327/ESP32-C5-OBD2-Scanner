import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import '../transport/diag.dart';

/// Итог одного блока в сохранённом скане. Тексты ошибок не храним: их даёт база знаний
/// при показе, поэтому новые переводы видны и в старых сканах.
class SavedEcu {
  SavedEcu({
    required this.tx,
    required this.answered,
    required this.time,
    this.proto,
    this.model,
    this.modelChosen = false,
    this.part,
    this.variant,
    this.dtcs = const [],
  });

  final int tx; // адрес запроса — по нему блок находится в базе знаний
  final bool answered;
  final DateTime time; // когда опрошен: у пересканированного блока позже, чем у скана
  final String? proto; // kwp / uds
  final String? model;
  final bool modelChosen; // модель выбрана руками
  final String? part;
  final String? variant;
  final List<Dtc> dtcs;

  Map<String, dynamic> toJson() => {
        'tx': tx,
        'answered': answered,
        'time': time.millisecondsSinceEpoch,
        if (proto != null) 'proto': proto,
        if (model != null) 'model': model,
        if (modelChosen) 'modelChosen': true,
        if (part != null) 'part': part,
        if (variant != null) 'variant': variant,
        'dtcs': [
          for (final d in dtcs) {'raw': d.raw, 'status': d.status, 'active': d.active}
        ],
      };

  factory SavedEcu.fromJson(Map<String, dynamic> j) => SavedEcu(
        tx: j['tx'] as int,
        answered: j['answered'] as bool? ?? false,
        time: DateTime.fromMillisecondsSinceEpoch(j['time'] as int),
        proto: j['proto'] as String?,
        model: j['model'] as String?,
        modelChosen: j['modelChosen'] as bool? ?? false,
        part: j['part'] as String?,
        variant: j['variant'] as String?,
        dtcs: [
          for (final d in (j['dtcs'] as List? ?? const []))
            Dtc([for (final b in d['raw'] as List) b as int], d['status'] as int, active: d['active'] as bool?)
        ],
      );
}

/// Скан машины, как он сохранён на телефоне: все блоки базы знаний, ответившие и нет.
class SavedScan {
  SavedScan({
    required this.id,
    required this.time,
    required this.ecus,
    this.module,
    this.vin,
    this.batteryMv = 0,
    this.fw = '',
  });

  final String id;
  final DateTime time;
  final List<SavedEcu> ecus;

  /// null — автоскан всех блоков; иначе пересканирован один блок (узел, «BSI»),
  /// остальные перенесены из предыдущего скана.
  final String? module;
  final String? vin;
  final int batteryMv;
  final String fw;

  Iterable<SavedEcu> get answered => ecus.where((e) => e.answered);
  int get faults => answered.fold(0, (n, e) => n + e.dtcs.length);
  SavedEcu? ecu(int tx) => ecus.where((e) => e.tx == tx).firstOrNull;

  /// Тот же скан, где один блок опрошен заново.
  SavedScan withEcu(SavedEcu e, {required String module, required int batteryMv, required String fw}) => SavedScan(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        time: e.time,
        module: module,
        vin: vin,
        batteryMv: batteryMv,
        fw: fw,
        ecus: [
          for (final x in ecus) x.tx == e.tx ? e : x,
          if (ecu(e.tx) == null) e,
        ],
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'time': time.millisecondsSinceEpoch,
        if (module != null) 'module': module,
        if (vin != null) 'vin': vin,
        'mv': batteryMv,
        'fw': fw,
        'ecus': [for (final e in ecus) e.toJson()],
      };

  factory SavedScan.fromJson(Map<String, dynamic> j) => SavedScan(
        id: j['id'] as String,
        time: DateTime.fromMillisecondsSinceEpoch(j['time'] as int),
        module: j['module'] as String?,
        vin: j['vin'] as String?,
        batteryMv: j['mv'] as int? ?? 0,
        fw: j['fw'] as String? ?? '',
        ecus: [for (final e in j['ecus'] as List) SavedEcu.fromJson(e as Map<String, dynamic>)],
      );
}

/// Сканы на телефоне: папка на машину, файл на скан, хранятся [keep] последних.
class ScanStore {
  ScanStore({Future<Directory> Function()? base}) : _base = base ?? getApplicationDocumentsDirectory;
  final Future<Directory> Function() _base;

  static const keep = 10;

  Future<Directory> _dir(String carKey) async => Directory('${(await _base()).path}/scans/$carKey');

  /// Сканы машины, новые первыми. Битый файл пропускаем.
  Future<List<SavedScan>> list(String carKey) async {
    final d = await _dir(carKey);
    if (!d.existsSync()) return [];
    final out = <SavedScan>[];
    for (final f in d.listSync().whereType<File>().where((f) => f.path.endsWith('.json'))) {
      try {
        out.add(SavedScan.fromJson(jsonDecode(await f.readAsString()) as Map<String, dynamic>));
      } catch (_) {}
    }
    out.sort((a, b) => b.time.compareTo(a.time));
    return out;
  }

  /// Сохранить и убрать самые старые сверх [keep].
  Future<void> save(String carKey, SavedScan s) async {
    final d = await _dir(carKey);
    if (!d.existsSync()) d.createSync(recursive: true);
    await File('${d.path}/${s.id}.json').writeAsString(jsonEncode(s.toJson()));
    for (final old in (await list(carKey)).skip(keep)) {
      final f = File('${d.path}/${old.id}.json');
      if (f.existsSync()) await f.delete();
    }
  }

  Future<void> removeAll(String carKey) async {
    final d = await _dir(carKey);
    if (d.existsSync()) await d.delete(recursive: true);
  }
}
