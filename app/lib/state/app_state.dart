import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../kb/knowledge_base.dart';
import '../kb/sensors.dart';
import '../theme.dart';
import '../transport/adapter_client.dart';
import 'diag_service.dart';
import 'garage.dart';

/// Глобальное состояние: язык, тема, адрес адаптера, подключение, напряжение.
/// Простой ChangeNotifier — без внешних пакетов состояния.
class AppState extends ChangeNotifier {
  AppState(this._prefs) {
    locale = Locale(_prefs.getString('lang') ?? 'ru');
    theme = AppThemeKind.values[_prefs.getInt('theme') ?? AppThemeKind.bright.index];
    adapterUrl = _prefs.getString('url') ?? 'ws://192.168.4.1:81/ws';
    final slots = _prefs.getStringList('gauges');
    if (slots != null && slots.length == defaultGaugeSlots.length) gaugeSlots = slots;
  }

  /// Какая вкладка открыта внизу (плитки на главном экране переключают её).
  final tab = ValueNotifier<int>(0);

  /// Датчики на экране «Датчики»: [0] — большой сверху, [1..4] — маленькие.
  List<String> gaugeSlots = List.of(defaultGaugeSlots);

  void setGaugeSlot(int i, String id) {
    gaugeSlots[i] = id;
    _prefs.setStringList('gauges', gaugeSlots);
    notifyListeners();
  }

  /// Гараж: машины, текущая машина, итоги их сканов.
  late final Garage garage = Garage(_prefs);
  CarProfile get car => garage.current;
  String? get vin => car.vin;
  int? get lastFaults => car.lastFaults;
  int? lastAnswered; // сколько блоков ответило в этом подключении

  /// Прочитали VIN: выбираем эту машину в гараже или заводим новую.
  void setVin(String v) {
    garage.onVin(v);
    notifyListeners();
  }

  void setScanResult({required int faults, required int answered}) {
    car.lastFaults = faults;
    car.lastScan = DateTime.now();
    lastAnswered = answered;
    garage.save();
    notifyListeners();
  }

  void selectCar(String id) {
    garage.select(id);
    lastAnswered = null;
    notifyListeners();
  }

  void updateCar(String id, {required String name, required String sub}) {
    final c = garage.cars.firstWhere((c) => c.id == id);
    c.name = name;
    c.sub = sub;
    garage.save();
    notifyListeners();
  }

  void removeCar(String id) {
    garage.remove(id);
    notifyListeners();
  }

  final SharedPreferences _prefs;
  final client = AdapterClient();

  Locale locale = const Locale('ru');
  AppThemeKind theme = AppThemeKind.bright;
  String adapterUrl = 'ws://192.168.4.1:81/ws';

  bool connecting = false;
  bool get connected => client.connected;
  String? connectError;
  String fw = '';
  int batteryMv = 0;

  KnowledgeBase? kb;
  DiagService? diag;
  StreamSubscription? _evSub;

  String get lang => locale.languageCode;

  static Future<AppState> create() async =>
      AppState(await SharedPreferences.getInstance());

  void setLocale(String code) {
    locale = Locale(code);
    _prefs.setString('lang', code);
    notifyListeners();
  }

  void setTheme(AppThemeKind t) {
    theme = t;
    _prefs.setInt('theme', t.index);
    notifyListeners();
  }

  void setUrl(String url) {
    adapterUrl = url.trim();
    _prefs.setString('url', adapterUrl);
    notifyListeners();
  }

  Future<void> connect() async {
    connecting = true;
    connectError = null;
    notifyListeners();
    try {
      final hello = await client.connect(adapterUrl);
      fw = hello['fw']?.toString() ?? '';
      batteryMv = (hello['mv'] as num?)?.toInt() ?? 0;
      kb ??= await KnowledgeBase.load('assets/kb/c3_ii.json');
      diag = DiagService(client, kb!);
      _evSub = client.events.listen(_onEvent);
    } catch (e) {
      connectError = e.toString();
    } finally {
      connecting = false;
      notifyListeners();
    }
  }

  void _onEvent(Map<String, dynamic> ev) {
    switch (ev['ev']) {
      case 'vbat':
        batteryMv = (ev['mv'] as num?)?.toInt() ?? batteryMv;
        notifyListeners();
        break;
      case 'down':
        connectError = ev['err']?.toString();
        notifyListeners();
        break;
    }
  }

  String get batteryText => (batteryMv / 1000).toStringAsFixed(1).replaceAll('.', ',');

  Future<void> disconnect() async {
    await _evSub?.cancel();
    _evSub = null;
    await client.close();
    notifyListeners();
  }

  @override
  void dispose() {
    _evSub?.cancel();
    client.close();
    super.dispose();
  }
}
