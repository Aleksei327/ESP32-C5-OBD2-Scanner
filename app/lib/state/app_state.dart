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
    gaugeMode = (_prefs.getInt('gaugeMode') ?? 0).clamp(0, 2);
    graphMain = _prefs.getStringList('graphMain') ?? List.of(defaultGraphMain);
    final gs = _prefs.getStringList('graphSlots');
    if (gs != null && gs.length == maxGraphs) graphSlots = gs;
    graphCount = (_prefs.getInt('graphCount') ?? 4).clamp(minGraphs, maxGraphs);
    final ns = _prefs.getStringList('numSlots');
    if (ns != null && ns.length == maxNumbers) numSlots = ns;
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

  /// Режим экрана «Датчики»: 0 — стрелки, 1 — цифры, 2 — графики.
  int gaugeMode = 0;
  void setGaugeMode(int m) {
    gaugeMode = m;
    _prefs.setInt('gaugeMode', m);
    notifyListeners();
  }

  /// Графики: главный сверху (до 5 датчиков сразу) и [graphCount] одиночных под ним.
  static const minGraphs = 2, maxGraphs = 10, maxOnMainGraph = 5;
  List<String> graphMain = List.of(defaultGraphMain);
  List<String> graphSlots = List.of(defaultGraphSlots);
  int graphCount = 4;

  void setGraphMain(List<String> ids) {
    graphMain = ids.take(maxOnMainGraph).toList();
    _prefs.setStringList('graphMain', graphMain);
    notifyListeners();
  }

  void setGraphSlot(int i, String id) {
    graphSlots[i] = id;
    _prefs.setStringList('graphSlots', graphSlots);
    notifyListeners();
  }

  void setGraphCount(int n) {
    graphCount = n.clamp(minGraphs, maxGraphs);
    _prefs.setInt('graphCount', graphCount);
    notifyListeners();
  }

  /// Цифры: плашки по порядку; на экране столько, сколько влезет.
  static const maxNumbers = 30;
  List<String> numSlots = List.of(defaultNumSlots);
  void setNumSlot(int i, String id) {
    numSlots[i] = id;
    _prefs.setStringList('numSlots', numSlots);
    notifyListeners();
  }

  /// Гараж: машины, текущая машина, итоги их сканов.
  late final Garage garage = Garage(_prefs);
  CarProfile get car => garage.current;
  String? get vin => car.vin;
  int? get lastFaults => car.lastFaults;
  int? get lastAnswered => car.lastModules; // сколько блоков ответило на последнем скане

  /// Итог последнего автоскана в этом подключении: экран «Блоки» показывает его,
  /// а не сканирует заново. Новый скан — по кнопке «Автоскан» или «обновить».
  List<EcuResult> scanResults = [];
  bool scanRequested = false;

  /// Кнопка «Автоскан»: открыть «Блоки» и опросить машину заново.
  void requestScan() {
    scanRequested = true;
    tab.value = 1;
  }

  /// Прочитали VIN: выбираем эту машину в гараже или заводим новую.
  void setVin(String v) {
    garage.onVin(v);
    notifyListeners();
  }

  void setScanResult({required int faults, required int answered}) {
    car.lastFaults = faults;
    car.lastModules = answered;
    car.lastScan = DateTime.now();
    garage.save();
    notifyListeners();
  }

  void selectCar(String id) {
    garage.select(id);
    scanResults = [];
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
      kb ??= await KnowledgeBase.load('assets/kb/c3_ii.json', extraDtc: 'assets/kb/c3_ii_dtc_gpl.json');
      diag = DiagService(client, kb!);
      scanResults = [];
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
