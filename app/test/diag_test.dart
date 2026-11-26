import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:scaner_app/kb/bits.dart';
import 'package:scaner_app/kb/knowledge_base.dart';
import 'package:scaner_app/state/diag_service.dart';
import 'package:scaner_app/state/garage.dart';
import 'package:scaner_app/state/scan_store.dart';
import 'package:scaner_app/transport/adapter_client.dart';
import 'package:scaner_app/transport/diag.dart';
import 'package:scaner_app/kb/live_table.dart';

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
  test('BSI refuses ambiguous tables and unknown field widths', () {
    expect(() => LiveTable.parse([1, 26, 26]), throwsFormatException);
    expect(() => LiveTable.parse([1, 26, 0xff, 1, 27]), throwsFormatException);
    final bsi = loadKb().ecus.firstWhere((d) => d.node == 'BSI').models.first;
    final record = bsi.recordsFor('A7_V1_2', 'live').singleWhere((r) => r.label == 'C1');
    expect(() => LiveTable.parse([1, 240]).decode(record, [0]), throwsFormatException);
  });

  test('BSI reads advertised indexes once, validates the record echo and packed lengths', () async {
    final kb = loadKb();
    final bsi = kb.ecus.firstWhere((d) => d.node == 'BSI');
    var busy = true;
    var wrongEcho = false;
    var shortData = false;
    final client = FakeClient((tx, req) {
      final key = hexStr(req).replaceAll(' ', '');
      if (key == '21C1' && busy) {
        busy = false;
        return [0x7f, 0x21, 0x21];
      }
      // pages as the car sends them: 75 C0 <80 | FF last> 00 00 <page> <n> <data> <2 check bytes>
      return switch (key) {
        '35C000000111' => [0x75, 0xc0, 0x80, 0, 0, 1, 3, 1, 0, 26, 0x12, 0x34],
        '35C000000211' => [0x75, 0xc0, 0x80, 0, 0, 2, 5, 27, 28, 0xff, 5, 7, 0x12, 0x34],
        '35C000000311' => [0x75, 0xc0, 0xff, 0, 0, 3, 3, 0xff, 0x0b, 0x1e, 0x12, 0x34],
        '21C1' when shortData => [0x61, 0xc1, 1],
        '21C1' => [0x61, wrongEcho ? 0xc2 : 0xc1, 1, 0, 97, 1],
        _ => null,
      };
    });
    final diag = DiagService(client, kb);
    diag.link(bsi)
      ..model = bsi.models.first
      ..variant = 'A7_V1_2';
    final recs = diag.records(bsi, 'live');
    final ac = recs.singleWhere((r) => r.label == 'C1');
    final values = await diag.readRecord(bsi, ac);
    expect(values.map((v) => v.$2.number), [1, 0, closeTo(9.7, .00001), 1]);
    expect(values[1].$1.key, 'STATUS_AIR_CONDITIONING_COMPRESSOR_CLUTCH');
    expect(await diag.readRecord(bsi, recs.singleWhere((r) => r.label == 'C8')), isEmpty);
    expect(client.sent.where((s) => s.contains(':35')).length, 3);
    expect(client.sent.where((s) => s.endsWith(':21C8')), isEmpty);
    expect((await diag.link(bsi).liveTable)!.groups, {
      0xc1: [0, 26, 27, 28],
      0xc5: [7],
      0xcb: [0x1e], // с последней страницы
    });
    wrongEcho = true;
    await expectLater(diag.readRecord(bsi, ac), throwsFormatException);
    shortData = true;
    await expectLater(diag.readRecord(bsi, ac), throwsFormatException);
  });

  test('BSI table exactly as the C3 II sent it (21.11.2026)', () async {
    const pages = [
      '75C08000000111002C473F4015162528292A3335363738429F0B',
      '75C080000002114345494A5E03050C0F21232F3031323B3C5BA8',
      '75C080000003113E41444860FF01051B1F141516171819008A4C',
      '75C080000004110103040708090C0D0E101A1C1D1EFF0250D602',
      '75C0800000051131393A4851525354636465666768696A6B0C82',
      '75C08000000611595A5B5F60615C5D5E02030405090A191A979D',
      '75C080000007111C1D2324262728292C2D32383B3C3D3E3F754A',
      '75C08000000811474F5556FF0512343D3F4F0C0D0F101314B0D2',
      '75C08000000911161C2021242526282A37384142494A4B4C9C3E',
      '75C08000000A114EFF060406FF070F10292A2F0406080A0CE9E5',
      '75C08000000B110D0E14161A1C1E2023282EFF084C2603045D14',
      '75C08000000C1105060708090A0B0C1F202D2E2F31323A3B1483',
      '75C08000000D113C3D4041424E5054FF093E451E2B2C2E3045F4',
      '75C08000000E113F414648491B1C2324262D477402141F3160CF',
      '75C08000000F11424344FF0A08010409FF0B1EFF0D0F2B03DC98',
      '75C0FF0000100E070B0C0D1113141516171A1B1E2EBB37',
    ];
    List<int> hex(String s) => [for (var i = 0; i < s.length; i += 2) int.parse(s.substring(i, i + 2), radix: 16)];
    final asked = <int>[];
    final table = await LiveTable.read((req) async {
      asked.add(req[4]);
      return hex(pages[req[4] - 1]);
    });
    expect(asked, List.generate(16, (i) => i + 1));
    expect(table.groups.keys, [0xc0, 0xc1, 0xc2, 0xc5, 0xc6, 0xc7, 0xc8, 0xc9, 0xca, 0xcb, 0xcd]);
    expect(table.groups[0xc1],
        [0x05, 0x1b, 0x1f, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x00, 0x01, 0x03, 0x04, 0x07, 0x08, 0x09, 0x0c, 0x0d, 0x0e, 0x10, 0x1a, 0x1c, 0x1d, 0x1e]);
    expect(table.groups[0xcd]!.last, 0x2e); // последняя страница тоже с данными

    // C1: три 16-битных, шесть байтовых, 15 битов → 14 байт
    final bsi = loadKb().ecus.firstWhere((d) => d.node == 'BSI').models.first;
    final c1 = bsi.recordsFor('A51_V1', 'live').singleWhere((r) => r.label == 'C1');
    final payload = List.filled(14, 0)
      ..[3] = 44 // давление хладагента 4,4 бар
      ..[12] = 0x01; // первый битовый — команда компрессора
    final v = {for (final (p, x) in table.decode(c1, payload)) p.key: x.number};
    expect(v.length, 24);
    expect(v['REFRIGERANT_PRESSURE'], closeTo(4.4, 1e-9));
    expect(v['AIR_CON_COMPRESSOR_COMMAND'], 1);
    expect(v['STATUS_AIR_CONDITIONING_COMPRESSOR_CLUTCH'], 0);
    expect(() => table.decode(c1, List.filled(13, 0)), throwsFormatException);
  });

  test('коды ошибок: UDS (3 байта) и KWP (2 байта + состояние)', () {
    expect(Dtc([0xC1, 0x00, 0x00], 0x08).code, 'U0100');
    expect(Dtc([0x01, 0x30, 0x00], 0x09).code, 'P0130');
    expect(Dtc([0x01, 0x30, 0x00], 0x09).active, true);
    expect(Dtc([0x90, 0x03, 0x00], 0x08).key, 'B1003-00');
    expect(Dtc([0x01, 0x30], 0x60, active: true).key, 'P0130');
  });

  test('KWP 17 FF 00: BSI шлёт коды без состояния, двигатель — с состоянием (ответы машины)', () async {
    Future<List<Dtc>> read(List<int> answer) =>
        Kwp(FakeClient((tx, req) => answer), 'B', 0x752, 0x652).readDtcs();
    final now = await read([0x57, 0x01, 0xF9, 0x94]); // BSI 22.11.2026
    expect(now.map((d) => d.psa), ['F994']);
    expect(now.single.active, isNull);
    expect(now.single.status, isNull);
    final nov2 = await read([0x57, 0x03, 0xA4, 0xC0, 0xF5, 0xFF, 0xF9, 0x94]); // BSI 02.11.2026
    expect(nov2.map((d) => d.psa), ['A4C0', 'F5FF', 'F994']);
    final eng = await read([0x57, 0x03, 0x11, 0x09, 0x01, 0x00, 0x08, 0x0A, 0xE0, 0x00, 0x1E]); // V34
    expect(eng.map((d) => d.code), ['P1109', 'P0008', 'U2000']);
    expect(eng.every((d) => d.active != null), true);
    expect(await read([0x57, 0x00]), isEmpty);
  });

  test('коды PSA: тип + номер; блоки с P-кодами ищут «P…»', () {
    final kb = loadKb()
      ..psa = {
        'types': {
          'A': {'ru': 'замыкание на плюс', 'en': 'short to battery', 'fr': 'Court-circuit au plus'},
        },
        'codes': {
          '4C0': {'fr': 'fr-4C0', 'ru': 'Задний правый габарит', 'check': 'fr-check', 'check_ru': 'Габаритный фонарь'},
          '9AB': {'fr': 'x (Circuit ouvert) y', 'ru': 'Икс (обрыв цепи)', 'typed': true},
          'P1109': {'fr': 'fr-P1109'},
        },
        'sections': [
          {'name': 'BECB', 'ru': 'датчик состояния АКБ', 'lo': 'FF0', 'hi': 'FFE'},
        ],
        'unknown': {'ru': 'Нет описания в списке PSA: раздел «{s}», номер {n}', 'en': 'No description: "{s}" {n}'},
      };
    (kb.psa['types'] as Map)['F'] = {'ru': 'без уточнения', 'en': 'unspecified', 'fr': 'Non caractérisé'};
    expect(kb.psaDtc([0xFF, 0xF9], 'U3FF9', 'ru', saeP: false)!.text,
        'Нет описания в списке PSA: раздел «датчик состояния АКБ», номер FF9 (без уточнения)');
    expect(Dtc([0xA4, 0xC0], 0xF5).psa, 'A4C0');
    expect(Dtc([0x01, 0x30, 0x00], 0x09).psa, isNull);
    final light = kb.psaDtc([0xA4, 0xC0], 'B24C0', 'ru', saeP: false)!;
    expect(light.text, 'Задний правый габарит (замыкание на плюс)');
    expect(light.check, 'Габаритный фонарь');
    expect(kb.psaDtc([0x04, 0xC0], 'P04C0', 'ru', saeP: false)!.text, 'Задний правый габарит');
    expect(kb.psaDtc([0xA9, 0xAB], 'B29AB', 'ru', saeP: false)!.text, 'Икс (обрыв цепи)');  // тип уже в тексте
    expect(kb.psaDtc([0x11, 0x09], 'P1109', 'ru', saeP: true)!.text, 'fr-P1109');
    expect(kb.psaDtc([0x04, 0xC0], 'P04C0', 'ru', saeP: true), isNull);  // у двигателя номер PSA не годится
    expect(kb.psaDtc([0x54, 0xC0], 'C14C0', 'ru', saeP: false), isNull);  // 5 — не тип PSA
    expect(kb.ecus.firstWhere((e) => e.node == 'CMM').saeP, isTrue);
    expect(kb.ecus.firstWhere((e) => e.node == 'BSI').saeP, isFalse);
  });

  test('сканы: сохраняются с ошибками, хранятся 10 последних, блок пересканируется отдельно', () async {
    final dir = Directory.systemTemp.createTempSync('scans');
    addTearDown(() => dir.deleteSync(recursive: true));
    final store = ScanStore(base: () async => dir);
    SavedScan scan(int i) => SavedScan(id: '$i', time: DateTime(2026, 11, 1).add(Duration(hours: i)), batteryMv: 12600, ecus: [
          SavedEcu(tx: 0x752, answered: true, time: DateTime(2026, 11, 1), model: 'BSI', dtcs: [Dtc([0xA4, 0xC0], 0xF5, active: true)]),
          SavedEcu(tx: 0x6A8, answered: false, time: DateTime(2026, 11, 1)),
        ]);
    for (var i = 0; i < 12; i++) {
      await store.save('car', scan(i));
    }
    final list = await store.list('car');
    expect(list.map((s) => s.id), [for (var i = 11; i >= 2; i--) '$i']); // новые первыми, два старых ушли
    final s = list.first;
    expect(s.faults, 1);
    expect(s.ecu(0x752)!.dtcs.single.psa, 'A4C0');
    expect(s.ecu(0x752)!.dtcs.single.active, isTrue);
    expect(s.batteryMv, 12600);

    // пересканировали BSI — ошибки нет; остальное из прошлого скана, сам скан новый
    final again = s.withEcu(SavedEcu(tx: 0x752, answered: true, time: DateTime(2026, 11, 2), model: 'BSI'),
        module: 'BSI', batteryMv: 14100, fw: 'sim');
    expect(again.id, isNot(s.id));
    expect(again.module, 'BSI');
    expect(again.faults, 0);
    expect(again.ecu(0x6A8)!.answered, isFalse);
    expect(s.faults, 1); // прошлый скан не тронут
    expect(isSimulatorVin('VF7SIMULATORC3001'), isTrue);
    expect(isSimulatorVin('VF7AAAAAAAA000000'), isFalse);
  });

  test('гараж: удаляется любая машина, пустой гараж, первый VIN даёт имя', () async {
    SharedPreferences.setMockInitialValues({});
    final g = Garage(await SharedPreferences.getInstance());
    expect(g.real, isEmpty); // новый телефон — пустой гараж
    g.onVin('VF7AAAAAAB0000000'); // 10-й знак «B» — 2011
    expect(g.real.single.name, 'Citroën');
    expect(g.real.single.sub, '2011');
    g.onVin('VF3AAAAAAC0000000'); // другая машина — новая запись
    expect(g.real.length, 2);
    g.remove(g.current.id);
    g.remove(g.real.single.id); // и последнюю тоже
    expect(g.real, isEmpty);
    expect(g.current.blank, isTrue);
    g.onVin('VF7SIMULATORC3001'); // симулятор не занимает пустую заготовку
    expect(g.real.single.vin, 'VF7SIMULATORC3001');
    g.clear();
    expect(g.real, isEmpty);
  });

  test('сброс ошибок: на отказ 0x22 — сеанс, чтение, сброс; потом группа двигателя', () async {
    var clears = 0;
    final fake = FakeClient((tx, req) {
      if (tx != 0x6A8) return null;
      final h = hexStr(req).replaceAll(' ', '');
      if (h == '81') return [0xC1, 0xD0, 0x8F];
      if (h == '17FF00') return [0x57, 0x00];
      if (h == '14FF00') {
        clears++;
        return [0x7F, 0x14, 0x22]; // этот блок «все» не стирает
      }
      if (h == '140000') return [0x54, 0x00, 0x00];
      return [0x7F, req.first, 0x31];
    });
    final kb = loadKb();
    final diag = DiagService(fake, kb);
    final eng = kb.ecus.firstWhere((e) => e.node == 'CMM');
    await diag.rescan(eng); // как после автоскана: сеанс 81 открыт
    fake.sent.clear();
    expect(await diag.clearFaults(eng), '81 → 14 00 00');
    expect(clears, 2); // 10 C0 этот блок не знает — до сброса в той попытке не дошло
    expect(fake.sent, [
      '6A8:14FF00', '6A8:81', '6A8:17FF00', '6A8:14FF00', '6A8:81', '6A8:10C0', //
      '6A8:81', '6A8:140000',
    ]);

    // как на машине: 0x22 на всё, 14 00 00 — «не поддерживается»; в итоге причина — первый отказ
    final car = FakeClient((tx, req) {
      if (tx != 0x6A8) return null;
      final h = hexStr(req).replaceAll(' ', '');
      if (h == '81') return [0xC1, 0xD0, 0x8F];
      if (h == '17FF00') return [0x57, 0x00];
      if (h == '10C0') return [0x50, 0xC0];
      if (h == '140000') return [0x7F, 0x14, 0x12];
      return [0x7F, req.first, 0x22];
    });
    final d3 = DiagService(car, kb);
    await d3.rescan(eng);
    expect(() => d3.clearFaults(eng), throwsA(isA<NegativeResponse>().having((e) => e.code, 'code', 0x22)));

    // другой отказ — без запасных способов, сразу ошибка
    final strict = FakeClient((tx, req) => tx == 0x6A8 ? (req.first == 0x81 ? [0xC1, 0xD0, 0x8F] : [0x7F, req.first, 0x33]) : null);
    final d2 = DiagService(strict, kb);
    await d2.rescan(eng);
    expect(() => d2.clearFaults(eng), throwsA(isA<NegativeResponse>().having((e) => e.code, 'code', 0x33)));
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
