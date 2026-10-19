import 'dart:typed_data';

/// Положение значения в ответе блока, как пишет PSA-RE: `<байт>.<бит>`.
/// Байты считаются с 1 (первый байт данных после номера записи), биты — с 7
/// (старший, уходит первым) до 0. Диапазон `1.7-2.0` — 16 бит, байт 1 старший.
/// `3.7-n` — всё с 3-го байта до конца ответа.
class Bits {
  Bits(this.start, this.end);

  /// Номер первого и последнего бита в потоке (0 — байт 1, бит 7); end == null — до конца.
  final int start;
  final int? end;

  static int _pos(String s) {
    final p = s.split('.');
    return (int.parse(p[0]) - 1) * 8 + (7 - int.parse(p[1]));
  }

  factory Bits.parse(String s) {
    final i = s.indexOf('-');
    if (i < 0) {
      final p = _pos(s);
      return Bits(p, p);
    }
    final a = s.substring(0, i), b = s.substring(i + 1);
    return Bits(_pos(a), b == 'n' ? null : _pos(b));
  }

  int _last(int len) => end ?? len * 8 - 1;
  int length(int len) => _last(len) - start + 1;

  /// Хватает ли байтов ответа на это значение.
  bool fits(List<int> p) => start < p.length * 8 && _last(p.length) < p.length * 8 && _last(p.length) >= start;

  /// Целое без знака, старший бит первый.
  int uint(List<int> p) {
    var v = 0;
    for (var i = start; i <= _last(p.length); i++) {
      v = v * 2 + ((p[i >> 3] >> (7 - (i & 7))) & 1);
    }
    return v;
  }

  /// Целое со знаком (дополнительный код на всю длину поля).
  int sint(List<int> p) {
    final n = length(p.length);
    final v = uint(p);
    return v >= (1 << (n - 1)) ? v - (1 << n) : v;
  }

  /// Байты, которые накрывает поле (для строк, BCD, сырых байтов).
  List<int> bytes(List<int> p) => p.sublist(start >> 3, (_last(p.length) >> 3) + 1);
}

/// BCD: каждая тетрада — цифра (номера деталей PSA так и хранятся).
String bcd(List<int> b) =>
    b.map((x) => (x >> 4).toRadixString(16) + (x & 0xF).toRadixString(16)).join().toUpperCase();

String ascii(List<int> b) => String.fromCharCodes(b.where((c) => c >= 0x20 && c < 0x7F)).trim();

String hexStr(List<int> b) => b.map((x) => x.toRadixString(16).padLeft(2, '0')).join(' ').toUpperCase();

double float32(List<int> b) => b.length < 4 ? double.nan : ByteData.sublistView(Uint8List.fromList(b.sublist(0, 4))).getFloat32(0);
