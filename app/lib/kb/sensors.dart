/// Каталог датчиков для экрана «Датчики».
/// Стандартные параметры OBD-II (режим 01, SAE J1979) — есть почти у любой машины
/// с 2001 г. (бензин в ЕС), формулы общие. Плюс напряжение АКБ от самого адаптера.
/// Параметры конкретной марки (DID по шине 3/8) добавим из базы знаний позже.
class Sensor {
  const Sensor(this.id, this.ru, this.en, this.unit, this.min, this.max,
      {this.pid, this.red, this.decimals = 0, required this.decode});

  final String id;
  final String ru, en;
  final String unit;
  final double min, max;
  final double? red; // откуда начинается красная зона
  final int decimals;
  final int? pid; // null — значение не из OBD (напряжение адаптера)
  final double Function(List<int> b) decode;

  String name(String lang) => lang == 'en' ? en : ru;
}

double _a(List<int> b) => b[0].toDouble();
double _ab(List<int> b) => ((b[0] << 8) | b[1]).toDouble();

final List<Sensor> sensorCatalog = [
  Sensor('rpm', 'Обороты', 'Engine speed', 'rpm', 0, 7000, pid: 0x0C, red: 6000, decode: (b) => _ab(b) / 4),
  Sensor('speed', 'Скорость', 'Speed', 'km/h', 0, 200, pid: 0x0D, decode: _a),
  Sensor('coolant', 'Охлаждающая', 'Coolant', '°C', 40, 120, pid: 0x05, red: 105, decode: (b) => _a(b) - 40),
  Sensor('battery', 'Бортсеть', 'Supply', 'V', 10, 16, red: 15, decimals: 1, decode: _a),
  Sensor('load', 'Нагрузка', 'Engine load', '%', 0, 100, pid: 0x04, decode: (b) => _a(b) * 100 / 255),
  Sensor('throttle', 'Дроссель', 'Throttle', '%', 0, 100, pid: 0x11, decode: (b) => _a(b) * 100 / 255),
  Sensor('intake', 'Воздух на впуске', 'Intake air', '°C', -20, 80, pid: 0x0F, decode: (b) => _a(b) - 40),
  Sensor('map', 'Давление во впуске', 'Manifold pressure', 'kPa', 0, 110, pid: 0x0B, decode: _a),
  Sensor('maf', 'Расход воздуха', 'Air flow', 'g/s', 0, 50, pid: 0x10, decimals: 1, decode: (b) => _ab(b) / 100),
  Sensor('timing', 'Опережение зажигания', 'Timing advance', '°', -10, 50, pid: 0x0E, decode: (b) => _a(b) / 2 - 64),
  Sensor('stft', 'Коррекция топлива', 'Fuel trim (short)', '%', -25, 25, pid: 0x06, decimals: 1, decode: (b) => _a(b) * 100 / 128 - 100),
  Sensor('fuel', 'Уровень топлива', 'Fuel level', '%', 0, 100, pid: 0x2F, decode: (b) => _a(b) * 100 / 255),
  Sensor('ambient', 'Снаружи', 'Ambient', '°C', -20, 50, pid: 0x46, decode: (b) => _a(b) - 40),
  Sensor('ecu_volt', 'Напряжение ЭБУ', 'ECU voltage', 'V', 10, 16, pid: 0x42, red: 15, decimals: 1, decode: (b) => _ab(b) / 1000),
];

Sensor sensorById(String id) =>
    sensorCatalog.firstWhere((s) => s.id == id, orElse: () => sensorCatalog.first);

/// Что стоит на экране по умолчанию: большой сверху + четыре маленьких.
const defaultGaugeSlots = ['rpm', 'speed', 'coolant', 'battery', 'load'];

/// Графики: главный (несколько линий) и одиночные под ним.
const defaultGraphMain = ['rpm', 'speed'];
const defaultGraphSlots = ['rpm', 'speed', 'coolant', 'battery', 'load', 'throttle', 'intake', 'map', 'maf', 'timing'];

/// Цифры: весь каталог по порядку, дальше по кругу.
final defaultNumSlots = [for (var i = 0; i < 30; i++) sensorCatalog[i % sensorCatalog.length].id];
