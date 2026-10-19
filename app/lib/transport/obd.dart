import 'adapter_client.dart';
import 'diag.dart';

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
