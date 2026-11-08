import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// Журнал обмена с блоками: каждая строка — время и запрос, ответ или ошибка.
/// Лежит в папке приложения на общей памяти (Android/data/<пакет>/files/diag_log.txt),
/// её можно забрать по USB (`adb pull`). Больше 1 МБ — старый файл уходит в .1.
class DiagLog {
  DiagLog._();
  static final instance = DiagLog._();

  static const maxBytes = 1 << 20;
  File? _file;
  Future<void> _queue = Future.value();

  String? get path => _file?.path;

  Future<void> init() async {
    try {
      final dir = await getExternalStorageDirectory() ?? await getApplicationDocumentsDirectory();
      _file = File('${dir.path}/diag_log.txt');
    } catch (_) {
      _file = null; // нет доступа к памяти (тесты) — без журнала
    }
  }

  /// Записать строку; записи идут по очереди, ошибки записи не мешают работе.
  void add(String line) {
    final f = _file;
    if (f == null) return;
    final text = '${DateTime.now().toIso8601String()} $line\n';
    _queue = _queue.then((_) async {
      try {
        if (await f.exists() && await f.length() > maxBytes) await f.rename('${f.path}.1');
        await f.writeAsString(text, mode: FileMode.append);
      } catch (_) {}
    });
  }
}
