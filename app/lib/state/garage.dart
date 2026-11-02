import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Машина в гараже. Фото лежат в папке по [id] (см. PhotoStore).
class CarProfile {
  CarProfile({required this.id, this.vin, required this.name, this.sub = '', this.lastScan, this.lastFaults, this.lastModules});

  final String id;
  String? vin;
  String name;
  String sub; // мотор, год — пишет пользователь
  DateTime? lastScan;
  int? lastFaults;
  int? lastModules; // сколько блоков ответило на последнем скане

  /// Заготовка пустого гаража: ни имени, ни VIN, ни скана. Первый автоскан сделает её машиной.
  bool get blank => vin == null && name.isEmpty && lastScan == null;

  Map<String, dynamic> toJson() => {
        'id': id,
        'vin': vin,
        'name': name,
        'sub': sub,
        'lastScan': lastScan?.millisecondsSinceEpoch,
        'lastFaults': lastFaults,
        'lastModules': lastModules,
      };

  factory CarProfile.fromJson(Map<String, dynamic> j) => CarProfile(
        id: j['id'] as String,
        vin: j['vin'] as String?,
        name: j['name'] as String? ?? '?',
        sub: j['sub'] as String? ?? '',
        lastScan: j['lastScan'] == null ? null : DateTime.fromMillisecondsSinceEpoch(j['lastScan'] as int),
        lastFaults: j['lastFaults'] as int?,
        lastModules: j['lastModules'] as int?,
      );
}

/// Список машин и какая сейчас выбрана; хранится в настройках телефона.
class Garage {
  Garage(this._prefs) {
    final raw = _prefs.getString('garage');
    if (raw != null) {
      cars = [for (final j in jsonDecode(raw) as List) CarProfile.fromJson(j as Map<String, dynamic>)];
    }
    if (cars.isEmpty) cars.add(_blank());
    currentId = _prefs.getString('garageCurrent') ?? cars.first.id;
    if (!cars.any((c) => c.id == currentId)) currentId = cars.first.id;
  }

  final SharedPreferences _prefs;
  List<CarProfile> cars = [];
  late String currentId;

  CarProfile get current => cars.firstWhere((c) => c.id == currentId);

  /// Машины для списка в гараже (без пустой заготовки).
  Iterable<CarProfile> get real => cars.where((c) => !c.blank);

  static CarProfile _blank() => CarProfile(id: 'car${DateTime.now().millisecondsSinceEpoch}', name: '');

  void save() {
    _prefs.setString('garage', jsonEncode([for (final c in cars) c.toJson()]));
    _prefs.setString('garageCurrent', currentId);
  }

  void select(String id) {
    currentId = id;
    save();
  }

  /// Прочитали VIN из машины. Возвращает true, если машина новая.
  bool onVin(String vin) {
    final known = cars.where((c) => c.vin == vin);
    if (known.isNotEmpty) {
      currentId = known.first.id;
      save();
      return false;
    }
    if (current.vin == null && !isSimulatorVin(vin)) {
      current.vin = vin; // у текущей машины VIN ещё не было — это она
      if (current.name.isEmpty) {
        current.name = brandFromVin(vin); // пустой гараж: имя по VIN, поправить можно руками
        current.sub = yearFromVin(vin) ?? '';
      }
      save();
      return false;
    }
    final car = CarProfile(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      vin: vin,
      name: brandFromVin(vin),
      sub: yearFromVin(vin) ?? '',
    );
    cars.add(car);
    currentId = car.id;
    save();
    return true;
  }

  /// Удалить машину; последнюю тоже — гараж станет пустым.
  void remove(String id) {
    cars.removeWhere((c) => c.id == id);
    if (!cars.any((c) => !c.blank)) cars = [cars.where((c) => c.blank).firstOrNull ?? _blank()];
    if (!cars.any((c) => c.id == currentId)) currentId = cars.first.id;
    save();
  }

  /// Удалить все машины: остаётся пустой гараж.
  void clear() {
    cars = [_blank()];
    currentId = cars.first.id;
    save();
  }
}

/// VIN симулятора адаптера (sim/c3_sim.py): своя машина в гараже, чужой VIN не занимает.
bool isSimulatorVin(String vin) => vin.toUpperCase().contains('SIMULATOR');

/// Марка по первым трём знакам VIN (WMI) — самые частые в Европе.
String brandFromVin(String vin) {
  const wmi = {
    'VF7': 'Citroën', 'VF3': 'Peugeot', 'VR3': 'Peugeot', 'VR7': 'Citroën', 'VF1': 'Renault', 'VF6': 'Renault',
    'UU1': 'Dacia', 'WVW': 'Volkswagen', 'WV1': 'Volkswagen', 'WV2': 'Volkswagen', 'WAU': 'Audi', 'WBA': 'BMW',
    'WDB': 'Mercedes-Benz', 'WDD': 'Mercedes-Benz', 'W0L': 'Opel', 'VSS': 'SEAT', 'TMB': 'Škoda', 'ZFA': 'Fiat',
    'SAL': 'Land Rover', 'JTD': 'Toyota', 'VNK': 'Toyota', 'SB1': 'Toyota', 'KMH': 'Hyundai', 'TMA': 'Hyundai',
    'KNA': 'Kia', 'U5Y': 'Kia', 'JN1': 'Nissan', 'SJN': 'Nissan', 'VNV': 'Nissan', 'WF0': 'Ford', 'JMZ': 'Mazda',
    'YV1': 'Volvo', 'VF8': 'DS', 'XTA': 'Lada',
  };
  return wmi[vin.length >= 3 ? vin.substring(0, 3).toUpperCase() : ''] ?? 'VIN …${vin.length > 6 ? vin.substring(vin.length - 6) : vin}';
}

/// Модельный год по 10-му знаку VIN (цикл 2010–2039; у старых машин может врать).
String? yearFromVin(String vin) {
  if (vin.length < 10) return null;
  const codes = 'ABCDEFGHJKLMNPRSTVWXY123456789';
  final i = codes.indexOf(vin[9].toUpperCase());
  return i < 0 ? null : '${2010 + i}';
}
