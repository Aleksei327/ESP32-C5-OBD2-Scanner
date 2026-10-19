import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scaner_app/kb/bits.dart';
import 'package:scaner_app/kb/knowledge_base.dart';
import 'package:scaner_app/state/diag_service.dart';
import 'package:scaner_app/transport/adapter_client.dart';
import 'package:scaner_app/transport/diag.dart';

/// Адаптер-подставка: отвечает по таблице (шина, адрес, запрос) → ответ, остальное — молчание.
class FakeClient extends AdapterClient {
  FakeClient(this.answer);
  final List<int>? Function(int tx, List<int> req) answer;
  final sent = <String>[];

  @override
  Future<void> openBus(String bus, {bool listen = true, int bitrate = 500000}) async {}

  @override
  Future<List<int>> request(String bus, int tx, int rx, List<int> data, {int timeoutMs = 1500}) async {
    sent.add('${tx.toRadixString(16).toUpperCase()}:${hexStr(data).replaceAll(' ', '')}');
    final r = answer(tx, data);
    if (r == null) throw AdapterError('timeout');
    return r;
  }
}

KnowledgeBase loadKb() => KnowledgeBase(jsonDecode(File('assets/kb/c3_ii.json').readAsStringSync()) as Map<String, dynamic>);

void main() {
  test('коды ошибок: UDS (3 байта) и KWP (2 байта + состояние)', () {
    expect(Dtc([0xC1, 0x00, 0x00], 0x08).code, 'U0100');
    expect(Dtc([0x01, 0x30, 0x00], 0x09).code, 'P0130');
    expect(Dtc([0x01, 0x30, 0x00], 0x09).active, true);
    expect(Dtc([0x90, 0x03, 0x00], 0x08).key, 'B1003-00');
    expect(Dtc([0x01, 0x30], 0x60, active: true).key, 'P0130');
  });

  test('биты в нотации PSA-RE', () {
    final p = [0x03, 0x20, 0x8D, 0xFE, 0x41, 0x42];
    expect(Bits.parse('1.7-2.0').uint(p), 800);
    expect(Bits.parse('3.7').uint(p), 1);
    expect(Bits.parse('3.3-3.0').uint(p), 0xD);
    expect(Bits.parse('3.6-3.4').uint(p), 0);
    expect(Bits.parse('4.7-4.0').sint(p), -2);
    expect(Bits.parse('5.7-n').bytes(p), [0x41, 0x42]);
    expect(Bits.parse('1.7-8.0').fits(p), false);
    expect(bcd([0x96, 0x59, 0x28, 0x56, 0x80]), '9659285680');
  });

  test('значения: множитель, сдвиг, подписи', () {
    final temp = Param({'key': 'T', 'bits': '1.7-1.0', 'type': 'uint', 'offset': -50, 'units': '°C'});
    expect(temp.decode([140]).number, 90);
    final volt = Param({'key': 'V', 'bits': '1.7-1.0', 'factor': 0.1});
    expect(volt.decode([141]).number, closeTo(14.1, 1e-9));
    expect(volt.decimals, 1);
    final sup = Param({
      'key': 'S',
      'bits': '1.7-1.0',
      'type': 'enum',
      'values': {
        '3': {'en': 'BOSCH'}
      }
    });
    expect(txt(sup.decode([3]).label, 'ru'), 'BOSCH');
    expect(Param({'key': 'VIN', 'bits': '1.7-3.0', 'type': 'str'}).decode('VF7'.codeUnits).text, 'VF7');
  });

  test('база знаний C3 II собрана из PSA-RE', () {
    final kb = loadKb();
    final bsi = kb.ecus.firstWhere((e) => e.node == 'BSI');
    expect([bsi.tx, bsi.rx], [0x752, 0x652]);
    expect(bsi.protos.first, 'kwp');
    expect(bsi.kwpOpens.first, [0x10, 0xC0]);
    final cmm = kb.ecus.firstWhere((e) => e.node == 'CMM');
    final v46 = cmm.models.firstWhere((m) => m.name == 'V46');
    expect(v46.proto.first, 'kwp');
    expect(v46.variantOf('789168'), startsWith('A51'));
    expect(v46.recordsFor('A51_V1', 'live').map((r) => r.label), contains('C0'));
    expect(v46.dtcText('P0130', 'en'), isNotEmpty);
    expect(kb.ecus.firstWhere((e) => e.node == 'BVA').optional, true);
  });

  test('тексты ошибок: доп. файл ludwig-v и общие коды SAE', () {
    final kb = loadKb();
    final bsi = kb.ecus.firstWhere((e) => e.node == 'BSI').models.firstWhere((m) => m.name == 'BSI');
    expect(bsi.dtcText('U3534', 'ru'), isNull);
    kb.addDtcTexts(jsonDecode(File('assets/kb/c3_ii_dtc_gpl.json').readAsStringSync()) as Map<String, dynamic>);
    expect(bsi.dtcText('U3534', 'ru'), isNotEmpty);
    expect(kb.genericDtc('U0121', 'ru'), 'Нет связи: блок управления ABS');
    expect(kb.genericDtc('P0420-00', 'en'), 'Catalyst System Efficiency Below Threshold (Bank 1)');
    expect(kb.genericDtc('P0420', 'ru'), contains('катализатора'));
    // коды производителя и U3 (там у PSA свои ошибки BSI) общим текстом не описываем
    for (final c in ['P1000', 'U1000', 'B1003', 'U3000', 'U3534']) {
      expect(kb.genericDtc(c, 'en'), isNull, reason: c);
    }
  });

  test('автоскан: протокол, модель по номеру детали, ошибки KWP', () async {
    // BSI (10 C0) и двигатель V46 (81) отвечают, остальные молчат
    final fake = FakeClient((tx, req) {
      final h = hexStr(req).replaceAll(' ', '');
      if (tx == 0x752) {
        if (h == '10C0') return [0x50, 0xC0];
        if (h == '2180') return [0x61, 0x80, 0x96, 0x59, 0x28, 0x56, 0x80, ...List.filled(12, 0)];
        if (h == '17FF00') return [0x57, 0x00];
        return [0x7F, req.first, 0x31];
      }
      if (tx == 0x6A8) {
        if (h == '81') return [0xC1, 0xD0, 0x8F];
        if (h == '21FE') return [0x61, 0xFE, ...List.filled(21, 0), 0x78, 0x91, 0x68];
        if (h == '17FF00') return [0x57, 0x02, 0x01, 0x30, 0x60, 0x03, 0x00, 0x20];
        return [0x7F, req.first, 0x31];
      }
      return null;
    });
    final kb = loadKb();
    final diag = DiagService(fake, kb);
    final res = await diag.autoScan().toList();
    final ok = res.where((r) => r.answered).toList();
    expect(ok.map((r) => r.def.node), ['BSI', 'CMM']);

    final bsi = ok.first;
    expect(bsi.proto, isA<Kwp>());
    expect(bsi.model?.name, 'BSI');
    expect(bsi.part, '9659285680');

    final eng = ok.last;
    expect(eng.model?.name, 'V46');
    expect(eng.variant, startsWith('A51'));
    expect(eng.dtcs.map((d) => d.code), ['P0130', 'P0300']);
    expect(eng.dtcs.map((d) => d.active), [true, false]);
    expect(diag.dtcText(eng.def, eng.dtcs.first, 'en'), isNotEmpty);
    // сеанс открывается тем запросом, который блок понимает
    expect(fake.sent, contains('6A8:81'));
    expect(fake.sent, isNot(contains('6A8:10C0')));
  });
}
