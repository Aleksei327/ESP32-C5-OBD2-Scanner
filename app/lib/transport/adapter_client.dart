import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

/// Клиент «тупого» адаптера по протоколу DOCS/ПРОТОКОЛ.md.
///
/// Отправляет команды с нарастающим id и ждёт ответ с тем же id.
/// События (vbat, frames, bus) раздаёт через [events].
class AdapterClient {
  AdapterClient();

  WebSocketChannel? _ch;
  StreamSubscription? _sub;
  int _id = 0;
  final _pending = <int, Completer<Map<String, dynamic>>>{};
  final _events = StreamController<Map<String, dynamic>>.broadcast();

  Stream<Map<String, dynamic>> get events => _events.stream;
  bool get connected => _ch != null;

  Future<Map<String, dynamic>> connect(String url,
      {Duration timeout = const Duration(seconds: 6)}) async {
    await close();
    final ch = WebSocketChannel.connect(Uri.parse(url));
    await ch.ready.timeout(timeout);
    _ch = ch;
    _sub = ch.stream.listen(_onMessage, onError: _onDown, onDone: _onDown);
    return call('hello');
  }

  void _onMessage(dynamic raw) {
    final Map<String, dynamic> msg;
    try {
      msg = jsonDecode(raw as String) as Map<String, dynamic>;
    } catch (_) {
      return;
    }
    if (msg.containsKey('ev')) {
      _events.add(msg);
      return;
    }
    final id = msg['id'];
    final c = id is int ? _pending.remove(id) : null;
    c?.complete(msg);
  }

  void _onDown([Object? e, StackTrace? s]) {
    final err = e?.toString() ?? 'connection closed';
    for (final c in _pending.values) {
      if (!c.isCompleted) c.completeError(StateError(err));
    }
    _pending.clear();
    if (_ch != null) {
      _ch = null;
      _events.add({'ev': 'down', 'err': err});
    }
  }

  Future<Map<String, dynamic>> call(String cmd,
      {Map<String, dynamic> args = const {},
      Duration timeout = const Duration(seconds: 4)}) {
    final ch = _ch;
    if (ch == null) return Future.error(StateError('not connected'));
    final id = ++_id;
    final c = Completer<Map<String, dynamic>>();
    _pending[id] = c;
    ch.sink.add(jsonEncode({'id': id, 'cmd': cmd, ...args}));
    return c.future.timeout(timeout, onTimeout: () {
      _pending.remove(id);
      throw TimeoutException(cmd);
    });
  }

  Future<void> openBus(String bus, {bool listen = true, int bitrate = 500000}) =>
      call('bus.open', args: {'bus': bus, 'listen': listen, 'bitrate': bitrate});

  Future<void> closeBus(String bus) => call('bus.close', args: {'bus': bus});

  Future<void> monitor(String bus, {String mode = 'summary', List<String>? ids}) =>
      call('monitor.start',
          args: {'bus': bus, 'mode': mode, 'ids': ?ids});

  Future<void> monitorStop(String bus) => call('monitor.stop', args: {'bus': bus});

  /// Один запрос ISO-TP к блоку. Возвращает ответ блока в байтах (с 7F при отказе)
  /// или кидает [AdapterError], если не ответил адаптер (timeout, listen_only…).
  Future<List<int>> request(String bus, int tx, int rx, List<int> data,
      {int timeoutMs = 1500}) async {
    final r = await call('isotp.req',
        args: {
          'bus': bus,
          'tx': tx.toRadixString(16),
          'rx': rx.toRadixString(16),
          'data': _hex(data),
          'timeout_ms': timeoutMs,
        },
        timeout: Duration(milliseconds: timeoutMs + 1500));
    if (r['ok'] == true) return _unhex(r['data'] as String);
    throw AdapterError(r['err']?.toString() ?? 'unknown');
  }

  /// Запрос, когда адрес ответа неизвестен (поиск блоков): адаптер берёт первый
  /// ответ после запроса и сообщает, откуда он пришёл. Возвращает (rx, данные).
  Future<(int, List<int>)> requestAnyRx(String bus, int tx, List<int> data, {int timeoutMs = 100}) async {
    final r = await call('isotp.req',
        args: {'bus': bus, 'tx': tx.toRadixString(16), 'rx': '*', 'data': _hex(data), 'timeout_ms': timeoutMs},
        timeout: Duration(milliseconds: timeoutMs + 1500));
    if (r['ok'] != true) throw AdapterError(r['err']?.toString() ?? 'unknown');
    return (int.parse(r['rx'].toString(), radix: 16), _unhex(r['data'] as String));
  }

  Future<void> close() async {
    await _sub?.cancel();
    _sub = null;
    await _ch?.sink.close();
    _onDown();
  }

  static String _hex(List<int> b) =>
      b.map((x) => x.toRadixString(16).padLeft(2, '0')).join().toUpperCase();

  static List<int> _unhex(String s) => [
        for (var i = 0; i + 1 < s.length; i += 2) int.parse(s.substring(i, i + 2), radix: 16)
      ];
}

class AdapterError implements Exception {
  AdapterError(this.code);
  final String code;
  @override
  String toString() => 'AdapterError($code)';
}
