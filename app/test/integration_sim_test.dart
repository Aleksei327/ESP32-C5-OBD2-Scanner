@Tags(['sim'])
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:scaner_app/kb/knowledge_base.dart';
import 'package:scaner_app/state/diag_service.dart';
import 'package:scaner_app/transport/adapter_client.dart';
import 'package:scaner_app/transport/uds.dart';

/// Весь стек приложения (транспорт + UDS + диагностика) против живого симулятора.
///   python sim/c3_sim.py
///   flutter test --tags sim --run-skipped
void main() {
  test('подключение, автоскан, ошибки, настройки, OBD-II', () async {
    final kb = KnowledgeBase(_kb());
    final client = AdapterClient();
    final hello = await client.connect('ws://127.0.0.1:8765');
    expect(hello['ok'], true);

    final diag = DiagService(client, kb);
    final results = await diag.autoScan().toList();
    expect(results.where((r) => r.answered).length, 5);
    final bsi = results.firstWhere((r) => r.def.name == 'BSI');
    expect(bsi.dtcs.map((d) => d.code), containsAll(['U0100', 'U0155']));

    final id = await diag.identify(bsi.def);
    expect(id['vin'], isNotEmpty);

    final cfg = await diag.readConfig(bsi.def);
    expect(cfg.length, bsi.def.config.length);

    // стоп-кадр ошибки двигателя P0130
    final eng = results.firstWhere((r) => r.def.name == 'Двигатель');
    final p0130 = eng.dtcs.firstWhere((d) => d.code == 'P0130');
    final snap = await diag.readSnapshot(eng.def, p0130);
    expect(snap.map((s) => s.$1.did), containsAll([4097, 4098, 4102]));
    expect(snap.firstWhere((s) => s.$1.did == 4097).$2, 2140);

    // поиск блоков: 5 из базы + 2 «чужих» в симуляторе
    final steps = await diag.discover().toList();
    final found = steps.last.found.map((f) => f.$1).toSet();
    expect(found, containsAll([0x752, 0x6A8, 0x6AD, 0x744, 0x75F, 0x76D, 0x6B5]));
    // адрес ответа — настоящий, а не угаданный
    expect(steps.last.found, containsAll([(0x6A8, 0x688), (0x752, 0x652), (0x6AD, 0x68D)]));

    await client.openBus('A', listen: false);
    final obd = Obd(client);
    expect(await obd.rpm(), greaterThan(0));
    expect(await obd.vin(), id['vin']);

    await client.close();
  }, timeout: const Timeout(Duration(seconds: 120)));
}

Map<String, dynamic> _kb() => {
      'diag_bus': 'B',
      'dids': {
        '4097': {'name_ru': 'Обороты', 'unit': 'rpm', 'len': 2},
        '4098': {'name_ru': 'Охлаждающая', 'unit': '°C', 'len': 1, 'off': -40},
        '4099': {'name_ru': 'Дроссель', 'unit': '%', 'len': 1},
        '4101': {'name_ru': 'Бортсеть', 'unit': 'V', 'len': 2, 'scale': 0.001},
        '4102': {'name_ru': 'Скорость', 'unit': 'km/h', 'len': 1},
      },
      'ecus': [
        {
          'name': 'BSI', 'tx': '752', 'rx': '652',
          'idents': {'vin': 61840},
          'config': [
            {'did': 8705, 'name_ru': 'Закрывать двери', 'type': 'bool'},
            {'did': 8706, 'name_ru': 'ДХО', 'type': 'bool'},
          ]
        },
        {'name': 'Двигатель', 'tx': '6A8', 'rx': '688', 'idents': {'vin': 61840}},
        {'name': 'ABS/ESP', 'tx': '6AD', 'rx': '68D', 'idents': {'vin': 61840}},
        {'name': 'Подушки', 'tx': '744', 'rx': '644', 'idents': {'vin': 61840}},
        {'name': 'Щиток', 'tx': '75F', 'rx': '65F', 'idents': {'vin': 61840}},
      ],
    };
