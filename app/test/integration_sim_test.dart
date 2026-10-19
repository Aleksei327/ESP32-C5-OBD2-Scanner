@Tags(['sim'])
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scaner_app/kb/knowledge_base.dart';
import 'package:scaner_app/state/diag_service.dart';
import 'package:scaner_app/transport/adapter_client.dart';
import 'package:scaner_app/transport/diag.dart';
import 'package:scaner_app/transport/obd.dart';

/// Весь стек приложения (транспорт + KWP/UDS + диагностика + база знаний) против живого симулятора.
///   python sim/c3_sim.py
///   flutter test --tags sim --run-skipped
void main() {
  test('подключение, автоскан, опознание моделей, данные, ошибки, OBD-II', () async {
    final kb = KnowledgeBase(jsonDecode(File('assets/kb/c3_ii.json').readAsStringSync()) as Map<String, dynamic>);
    final client = AdapterClient();
    final hello = await client.connect('ws://127.0.0.1:8765');
    expect(hello['ok'], true);

    final diag = DiagService(client, kb);
    final results = await diag.autoScan().toList();
    final answered = {for (final r in results.where((r) => r.answered)) r.def.node: r};
    expect(answered.keys, unorderedEquals(['BSI', 'CMM', 'ABS', 'RBG', 'CMB']));
    // модели опознаны по номерам деталей
    expect({for (final r in answered.values) r.def.node: r.model?.name},
        {'BSI': 'BSI', 'CMM': 'V46', 'ABS': 'ESPMK100', 'RBG': 'SAC_AUTOLIV', 'CMB': 'CLUSTER'});
    expect(answered.values.every((r) => r.proto is Kwp), true);

    final bsi = answered['BSI']!;
    expect(bsi.dtcs.length, 2);
    final info = await diag.identify(bsi.def);
    expect(info.vin, 'VF7SIMULATORC3001');
    expect(await diag.carVin(answered.values.toList()), 'VF7SIMULATORC3001');

    // двигатель: ошибки с текстами и живые данные из записи C0
    final eng = answered['CMM']!;
    expect(eng.dtcs.map((d) => d.code), containsAll(['P0130', 'P0300']));
    expect(eng.dtcs.firstWhere((d) => d.code == 'P0130').active, true);
    expect(diag.dtcText(eng.def, eng.dtcs.first, 'en'), isNotEmpty);
    final c0 = diag.records(eng.def, 'live').firstWhere((r) => r.label == 'C0');
    final live = await diag.readRecord(eng.def, c0);
    final rpm = live.firstWhere((v) => v.$1.key == 'ENGINE_SPEED').$2.number!;
    expect(rpm, greaterThan(500));
    final cool = live.firstWhere((v) => v.$1.key == 'ENGINE_COOLANT_TEMPERATURE').$2.number!;
    expect(cool, inInclusiveRange(55, 95));
    // у KWP-блоков PSA стоп-кадра нет — пусто, без ошибки
    expect(await diag.readSnapshot(eng.def, eng.dtcs.first), isEmpty);

    // сеанс KWP гаснет через 5 с — приложение должно переоткрыть его само
    await Future.delayed(const Duration(seconds: 6));
    expect((await diag.readRecord(eng.def, c0)).isNotEmpty, true);

    // сброс: сохранённая уходит, та, что есть сейчас, остаётся
    await diag.clearFaults(eng.def);
    expect((await diag.readFaults(eng.def)).map((d) => d.code), ['P0130']);

    // поиск блоков: кто из базы и 2 «чужих» в симуляторе
    final steps = await diag.discover().toList();
    final found = steps.last.found.map((f) => f.$1).toSet();
    expect(found, containsAll([0x752, 0x6A8, 0x6AD, 0x744, 0x75F, 0x6B1, 0x77A]));
    // адрес ответа — настоящий, а не угаданный
    expect(steps.last.found, containsAll([(0x6A8, 0x688), (0x752, 0x652), (0x6B1, 0x691)]));

    await client.openBus('A', listen: false);
    final obd = Obd(client);
    expect(await obd.rpm(), greaterThan(0));
    expect(await obd.vin(), info.vin);

    await client.close();
  }, timeout: const Timeout(Duration(seconds: 180)));
}
