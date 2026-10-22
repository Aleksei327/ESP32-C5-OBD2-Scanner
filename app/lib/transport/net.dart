import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Сеть телефона (Android, android/…/NetBridge.kt).
///
/// Адаптер раздаёт Wi-Fi без интернета, интернет остаётся на мобильных данных. Чтобы запросы
/// к адаптеру шли именно в его Wi-Fi, перед подключением процесс привязывается к той сети,
/// в которой лежит адрес адаптера ([bindForHost]).
///
/// Удалённый помощник: телефон соединяет адаптер (по Wi-Fi) с посредником на компьютере
/// (через интернет) и передаёт сообщения протокола в обе стороны.
class Net {
  static const _m = MethodChannel('scaner/net');
  static const _ev = EventChannel('scaner/net/remote');

  static bool get _android => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  /// true — нашлась сеть Wi-Fi с этим адресом, и процесс к ней привязан.
  static Future<bool> bindForHost(String host) async {
    if (!_android) return false;
    try {
      return await _m.invokeMethod<bool>('bindForHost', {'host': host}) ?? false;
    } catch (_) {
      return false;  // нет Android-части (тесты на ПК) — работаем без привязки
    }
  }

  static Future<void> remoteStart(String adapterUrl, String relayUrl) =>
      _m.invokeMethod('remoteStart', {'adapter': adapterUrl, 'relay': relayUrl});

  static Future<void> remoteStop() => _m.invokeMethod('remoteStop');

  /// {state: connecting/on/off/error, msg, up, down} — up/down: сколько сообщений прошло
  /// к компьютеру и к адаптеру.
  static Stream<Map<String, dynamic>> remoteStatus() => _android
      ? _ev.receiveBroadcastStream().map((e) => Map<String, dynamic>.from(e as Map))
      : const Stream.empty();
}
