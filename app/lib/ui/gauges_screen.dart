import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../kb/sensors.dart';
import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../transport/obd.dart';
import 'widgets.dart';

/// Живые данные OBD-II, три вида:
/// стрелки — большой прибор сверху и четыре маленьких;
/// цифры — плашки с числами, сколько влезет на экран;
/// графики — главный сверху (до 5 датчиков линиями) и от 2 до 10 одиночных под ним.
/// Нажатие на прибор, плашку или график — выбрать датчик на этом месте.
class GaugesScreen extends StatefulWidget {
  const GaugesScreen({super.key});
  @override
  State<GaugesScreen> createState() => _GaugesScreenState();
}

class _GaugesScreenState extends State<GaugesScreen> {
  static const _historyLen = 150; // ~ минута при опросе раз в 400 мс

  late final AppState _app;
  Obd? _obd;
  Timer? _timer;
  bool _busy = false;
  Set<int>? _supported;
  final _values = <String, double>{};
  final _history = <String, List<double>>{};
  int _numVisible = 0; // сколько плашек с цифрами влезло (считается при раскладке)

  // запись лога в CSV
  DateTime? _recStart;
  List<String> _recIds = [];
  final _rows = <String>[];
  bool get _recording => _recStart != null;

  /// Что сейчас на экране — только это и опрашиваем.
  List<String> get _visibleIds => switch (_app.gaugeMode) {
        0 => _app.gaugeSlots,
        1 => _app.numSlots.take(_numVisible).toList(),
        _ => [..._app.graphMain, ..._app.graphSlots.take(_app.graphCount)],
      };

  void _startRec() {
    final t = AppLocalizations.of(context);
    _recIds = _visibleIds.toSet().toList();
    _rows
      ..clear()
      ..add(['t, s', for (final id in _recIds) '${sensorById(id).name(_app.lang)}, ${unitFor(sensorById(id), t, _app.lang)}']
          .join(';'));
    setState(() => _recStart = DateTime.now());
  }

  Future<void> _stopRec() async {
    final start = _recStart!;
    setState(() => _recStart = null);
    String two(int v) => v.toString().padLeft(2, '0');
    final stamp = '${start.year}${two(start.month)}${two(start.day)}_${two(start.hour)}${two(start.minute)}${two(start.second)}';
    final dir = Directory('${(await getApplicationDocumentsDirectory()).path}/logs');
    if (!dir.existsSync()) dir.createSync(recursive: true);
    final f = File('${dir.path}/log_$stamp.csv');
    // BOM — чтобы Excel сразу понял UTF-8 и кириллицу в заголовках
    const bom = '﻿', eol = '\r\n';
    await f.writeAsString('$bom${_rows.join(eol)}$eol');
    await SharePlus.instance.share(ShareParams(files: [XFile(f.path, mimeType: 'text/csv')]));
  }

  void _logRow() {
    if (!_recording) return;
    final secs = DateTime.now().difference(_recStart!).inMilliseconds / 1000;
    String num(double v, int d) => v.isNaN ? '' : v.toStringAsFixed(d).replaceAll('.', ',');
    _rows.add([num(secs, 1), for (final id in _recIds) num(_values[id] ?? double.nan, sensorById(id).decimals + 1)].join(';'));
  }

  @override
  void initState() {
    super.initState();
    _app = AppScope.read(context);
    _start();
  }

  Future<void> _start() async {
    try {
      await _app.client.openBus('A', listen: false);
      _obd = Obd(_app.client);
      final sup = await _obd!.supportedPids();
      if (!mounted) return;
      setState(() => _supported = sup);
      _timer = Timer.periodic(const Duration(milliseconds: 400), (_) => _tick());
    } catch (_) {
      if (mounted) setState(() => _supported = {});
    }
  }

  Future<void> _tick() async {
    final o = _obd;
    if (o == null || _busy) return;
    _busy = true;
    try {
      for (final id in {..._visibleIds, ..._recIds}) {
        final s = sensorById(id);
        double v;
        if (s.pid == null) {
          v = _app.batteryMv / 1000;
        } else {
          try {
            v = s.decode(await o.pid(s.pid!));
          } catch (_) {
            v = double.nan;
          }
        }
        _values[id] = v;
        final h = _history.putIfAbsent(id, () => []);
        h.add(v);
        if (h.length > _historyLen) h.removeAt(0);
      }
      _logRow();
      if (mounted) setState(() {});
    } finally {
      _busy = false;
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  /// Кнопка записи — одна плашка в красном контуре: «● Запись» / «■ REC 00:07».
  Widget _recButton(BuildContext context, AppLocalizations t) {
    const red = Color(0xFFE11D48);
    final on = _recording;
    return Tooltip(
      message: on ? t.stopLog : t.recordLog,
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: _supported == null ? null : (on ? _stopRec : _startRec),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          height: 38,
          padding: const EdgeInsets.symmetric(horizontal: 14),
          decoration: BoxDecoration(
            color: on ? red : red.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: red, width: 1.6),
            boxShadow: on ? [BoxShadow(color: red.withValues(alpha: 0.45), blurRadius: 14, offset: const Offset(0, 4))] : null,
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(on ? Icons.stop_rounded : Icons.fiber_manual_record, size: 18, color: on ? Colors.white : red),
            const SizedBox(width: 6),
            Text(on ? _recTime() : t.record,
                style: on ? mono(context, 14, color: Colors.white).copyWith(fontWeight: FontWeight.w600)
                          : const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: red)),
          ]),
        ),
      ),
    );
  }

  String _recTime() {
    final s = DateTime.now().difference(_recStart!).inSeconds;
    return 'REC ${(s ~/ 60).toString().padLeft(2, '0')}:${(s % 60).toString().padLeft(2, '0')}';
  }

  bool _available(Sensor s) => s.pid == null || (_supported?.contains(s.pid) ?? false);

  /// Выбрать один датчик (для прибора, плашки или графика).
  Future<String?> _pickOne(String current) {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final lang = _app.lang;
    return showModalBottomSheet<String>(
      context: context,
      backgroundColor: p.surface,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (c) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: MediaQuery.of(c).size.height * 0.7),
          child: ListView(shrinkWrap: true, children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
              child: Text(t.pickSensor, style: display(c, 18, w: FontWeight.w700)),
            ),
            for (final s in sensorCatalog.where(_available))
              ListTile(
                title: Text(s.name(lang), style: TextStyle(color: p.text)),
                subtitle: Text(unitFor(s, t, lang), style: TextStyle(color: p.textDim)),
                trailing: s.id == current ? Icon(Icons.check_circle, color: p.accent) : null,
                onTap: () => Navigator.pop(c, s.id),
              ),
          ]),
        ),
      ),
    );
  }

  /// Датчики на главном графике: галочками, до пяти.
  Future<void> _pickMain() async {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final lang = _app.lang;
    final sel = List.of(_app.graphMain);
    final ok = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: p.surface,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (c) => SafeArea(
        child: StatefulBuilder(
          builder: (c, set) => ConstrainedBox(
            constraints: BoxConstraints(maxHeight: MediaQuery.of(c).size.height * 0.75),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
                child: Row(children: [
                  Expanded(child: Text(t.pickSensorsMain(AppState.maxOnMainGraph), style: display(c, 18, w: FontWeight.w700))),
                  FilledButton(onPressed: sel.isEmpty ? null : () => Navigator.pop(c, true), child: Text(t.done)),
                ]),
              ),
              Flexible(
                child: ListView(shrinkWrap: true, children: [
                  for (final s in sensorCatalog.where(_available))
                    CheckboxListTile(
                      value: sel.contains(s.id),
                      title: Text(s.name(lang), style: TextStyle(color: p.text)),
                      subtitle: Text(unitFor(s, t, lang), style: TextStyle(color: p.textDim)),
                      onChanged: (on) => set(() {
                        if (on == true && sel.length < AppState.maxOnMainGraph) sel.add(s.id);
                        if (on == false) sel.remove(s.id);
                      }),
                    ),
                ]),
              ),
            ]),
          ),
        ),
      ),
    );
    if (ok == true) _app.setGraphMain(sel);
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final p = context.p;
    AppScope.of(context); // перестраиваться при смене датчиков/языка
    final mode = _app.gaugeMode;

    return Scaffold(
      appBar: AppBar(
        title: Text(t.gauges),
        backgroundColor: p.bg,
        actions: [
          Padding(padding: const EdgeInsets.only(right: 14), child: _recButton(context, t)),
        ],
      ),
      body: _supported == null
          ? const Center(child: CircularProgressIndicator())
          : Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Padding(padding: const EdgeInsets.fromLTRB(20, 4, 20, 0), child: _modeSwitch(context, t)),
                // подсказка — сразу под переключателем, а для графиков рядом ещё и «сколько графиков»
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 4),
                  child: Row(children: [
                    Icon(Icons.touch_app_outlined, size: 18, color: p.textDim),
                    const SizedBox(width: 8),
                    Expanded(child: Text(t.gaugesHint, style: TextStyle(fontSize: 13, color: p.textDim))),
                    if (mode == 2) _countStepper(context, t),
                  ]),
                ),
                Expanded(
                  child: switch (mode) {
                    0 => _arrows(context),
                    1 => _numbers(context, t),
                    _ => _graphs(context, t),
                  },
                ),
              ]),
    );
  }

  Widget _modeSwitch(BuildContext context, AppLocalizations t) {
    final p = context.p;
    Widget seg(String label, int m) {
      final on = _app.gaugeMode == m;
      return Expanded(
        child: GestureDetector(
          onTap: () => _app.setGaugeMode(m),
          child: Container(
            height: 42,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              gradient: on ? LinearGradient(colors: [p.accent, p.info]) : null,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(label, style: TextStyle(fontWeight: FontWeight.w600, color: on ? p.onAccent : p.textDim)),
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(color: p.surface, borderRadius: BorderRadius.circular(16), border: Border.all(color: p.border)),
      child: Row(children: [seg(t.arrows, 0), seg(t.numbers, 1), seg(t.graphs, 2)]),
    );
  }

  /// «− 4 +»: сколько одиночных графиков под главным.
  Widget _countStepper(BuildContext context, AppLocalizations t) {
    final p = context.p;
    final n = _app.graphCount;
    Widget btn(IconData i, VoidCallback? tap) => InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: tap,
          child: Container(
            width: 34,
            height: 34,
            alignment: Alignment.center,
            decoration: BoxDecoration(border: Border.all(color: p.border), borderRadius: BorderRadius.circular(10)),
            child: Icon(i, size: 18, color: tap == null ? p.border : p.text),
          ),
        );
    return Tooltip(
      message: t.graphsBelow,
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        btn(Icons.remove, n > AppState.minGraphs ? () => _app.setGraphCount(n - 1) : null),
        SizedBox(width: 30, child: Text('$n', textAlign: TextAlign.center, style: display(context, 17, w: FontWeight.w700))),
        btn(Icons.add, n < AppState.maxGraphs ? () => _app.setGraphCount(n + 1) : null),
      ]),
    );
  }

  // ---------- стрелки ----------

  Widget _arrows(BuildContext context) {
    final slots = _app.gaugeSlots;
    return ListView(padding: const EdgeInsets.fromLTRB(20, 6, 20, 20), children: [
      _bigGauge(context, slots[0]),
      const SizedBox(height: 12),
      GridView.count(
        crossAxisCount: 2,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        childAspectRatio: 1.22,
        children: [for (var i = 1; i < 5; i++) _smallGauge(context, i, slots[i])],
      ),
    ]);
  }

  Widget _bigGauge(BuildContext context, String id) {
    final t = AppLocalizations.of(context);
    final s = sensorById(id);
    final lang = _app.lang;
    final p = context.p;
    return GlowCard(
      tint: p.gaugeA,
      onTap: () async {
        final c = await _pickOne(id);
        if (c != null) _app.setGaugeSlot(0, c);
      },
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
      child: Column(children: [
        Text(s.name(lang), style: TextStyle(fontWeight: FontWeight.w600, color: p.gaugeA)),
        Gauge(
          value: _values[id] ?? double.nan,
          min: s.min,
          max: s.max,
          redFrom: s.red,
          label: s.name(lang),
          unit: unitFor(s, t, lang),
          decimals: s.decimals,
          size: 196,
          color: p.gaugeA,
        ),
      ]),
    );
  }

  static const _colors = [
    Color(0xFFF59E0B), Color(0xFF22C55E), Color(0xFF8B5CF6), Color(0xFF06B6D4), Color(0xFFEC4899),
    Color(0xFFEF4444), Color(0xFF84CC16), Color(0xFF14B8A6), Color(0xFFF97316), Color(0xFF6366F1),
  ];

  Widget _smallGauge(BuildContext context, int slot, String id) {
    final t = AppLocalizations.of(context);
    final s = sensorById(id);
    final lang = _app.lang;
    final c = _colors[(slot - 1) % _colors.length];
    return GlowCard(
      tint: c,
      onTap: () async {
        final x = await _pickOne(id);
        if (x != null) _app.setGaugeSlot(slot, x);
      },
      padding: const EdgeInsets.fromLTRB(6, 10, 6, 0),
      child: Column(children: [
        Text(s.name(lang),
            maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: c)),
        Expanded(
          child: LayoutBuilder(
            builder: (_, box) => Gauge(
              value: _values[id] ?? double.nan,
              min: s.min,
              max: s.max,
              redFrom: s.red,
              label: s.name(lang),
              unit: unitFor(s, t, lang),
              decimals: s.decimals,
              size: box.maxHeight < box.maxWidth ? box.maxHeight : box.maxWidth,
              color: c,
            ),
          ),
        ),
      ]),
    );
  }

  // ---------- цифры ----------

  static const _numGap = 10.0, _numTileMinH = 80.0, _side = 20.0;

  String _fmt(Sensor s, double? v) => v == null || v.isNaN ? '—' : v.toStringAsFixed(s.decimals).replaceAll('.', ',');

  /// Плашки с числами: ширина — под пятизначное число (обороты), сколько влезет в ширину
  /// и в высоту экрана, столько и показываем (но не больше, чем датчиков есть у машины).
  Widget _numbers(BuildContext context, AppLocalizations t) {
    final p = context.p;
    final lang = _app.lang;
    final valueStyle = display(context, 26, w: FontWeight.w700);
    final digits = TextPainter(
      text: TextSpan(text: '88888', style: valueStyle),
      textDirection: TextDirection.ltr,
      textScaler: MediaQuery.textScalerOf(context),
    )..layout();
    final minW = digits.width + 22;
    return LayoutBuilder(builder: (context, box) {
      final width = box.maxWidth - 2 * _side, height = box.maxHeight - 18;
      final cols = math.max(2, ((width + _numGap) / (minW + _numGap)).floor());
      final rows = math.max(1, ((height + _numGap) / (_numTileMinH + _numGap)).floor());
      final avail = sensorCatalog.where(_available).length;
      _numVisible = math.min(math.min(cols * rows, avail), AppState.maxNumbers);
      final w = (width - _numGap * (cols - 1)) / cols;
      // плашки растягиваем по высоте, чтобы заняли экран целиком
      final usedRows = (_numVisible / cols).ceil();
      final h = math.min(120.0, (height - _numGap * (usedRows - 1)) / math.max(usedRows, rows));
      return SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(_side, 6, _side, 12),
        child: Wrap(spacing: _numGap, runSpacing: _numGap, children: [
          for (var i = 0; i < _numVisible; i++)
            Builder(builder: (context) {
              final id = _app.numSlots[i];
              final s = sensorById(id);
              final c = _colors[i % _colors.length];
              return SizedBox(
                width: w,
                height: h,
                child: GlowCard(
                  tint: c,
                  onTap: () async {
                    final x = await _pickOne(id);
                    if (x != null) _app.setNumSlot(i, x);
                  },
                  padding: const EdgeInsets.fromLTRB(11, 8, 8, 8),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(s.name(lang),
                        maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: c)),
                    const Spacer(),
                    FittedBox(
                      fit: BoxFit.scaleDown,
                      alignment: Alignment.centerLeft,
                      child: Text(_fmt(s, _values[id]), style: valueStyle),
                    ),
                    Text(unitFor(s, t, lang), style: TextStyle(fontSize: 11, color: p.textDim)),
                  ]),
                ),
              );
            }),
        ]),
      );
    });
  }

  // ---------- графики ----------

  Widget _graphs(BuildContext context, AppLocalizations t) {
    return LayoutBuilder(builder: (context, box) {
      final n = _app.graphCount;
      final gap = n > 5 ? 6.0 : 10.0;
      final height = box.maxHeight - 18;
      // главный — сколько останется после маленьких (но не меньше 150 и не больше 280),
      // маленькие делят остальное: так от 2 до 10 графиков влезают на один экран
      final mainH = (height - n * (36 + gap)).clamp(150.0, 280.0);
      final small = ((height - mainH - gap * n) / n).clamp(34.0, 120.0);
      return ListView(padding: const EdgeInsets.fromLTRB(_side, 6, _side, 12), children: [
        SizedBox(height: mainH, child: _mainGraph(context, t)),
        for (var i = 0; i < n; i++) ...[
          SizedBox(height: gap),
          SizedBox(height: small, child: _graphCard(context, t, i, compact: small < 64)),
        ],
      ]);
    });
  }

  Widget _mainGraph(BuildContext context, AppLocalizations t) {
    final p = context.p;
    final lang = _app.lang;
    final ids = _app.graphMain;
    Color col(int i) => i == 0 ? p.gaugeA : _colors[(i - 1) % _colors.length];
    return GlowCard(
      tint: p.gaugeA,
      onTap: _pickMain,
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        // легенда: цвет, датчик, текущее значение
        Wrap(spacing: 14, runSpacing: 4, children: [
          for (var i = 0; i < ids.length; i++)
            Row(mainAxisSize: MainAxisSize.min, children: [
              Container(width: 10, height: 10, decoration: BoxDecoration(color: col(i), shape: BoxShape.circle)),
              const SizedBox(width: 6),
              Text(sensorById(ids[i]).name(lang), style: TextStyle(fontSize: 13, color: p.textDim)),
              const SizedBox(width: 6),
              Text('${_fmt(sensorById(ids[i]), _values[ids[i]])} ${unitFor(sensorById(ids[i]), t, lang)}',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: p.text)),
            ]),
        ]),
        const SizedBox(height: 8),
        Expanded(
          child: CustomPaint(
            painter: MultiSparkline([
              for (var i = 0; i < ids.length; i++)
                (_history[ids[i]] ?? const <double>[], sensorById(ids[i]).min, sensorById(ids[i]).max, col(i)),
            ], p.border),
          ),
        ),
      ]),
    );
  }

  Widget _graphCard(BuildContext context, AppLocalizations t, int slot, {bool compact = false}) {
    final p = context.p;
    final id = _app.graphSlots[slot];
    final s = sensorById(id);
    final lang = _app.lang;
    final c = _colors[slot % _colors.length];
    return GlowCard(
      tint: c,
      onTap: () async {
        final x = await _pickOne(id);
        if (x != null) _app.setGraphSlot(slot, x);
      },
      padding: compact ? const EdgeInsets.fromLTRB(12, 3, 12, 3) : const EdgeInsets.fromLTRB(14, 6, 14, 6),
      // мало места — в строку: название и число слева, линия справа
      child: compact
          ? Row(children: [
              Expanded(
                flex: 5,
                child: Row(children: [
                  Expanded(child: Text(s.name(lang), maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, color: p.textDim))),
                  Text(_fmt(s, _values[id]), style: display(context, 15, w: FontWeight.w700)),
                  const SizedBox(width: 3),
                  Text(unitFor(s, t, lang), style: TextStyle(fontSize: 10, color: p.textDim)),
                ]),
              ),
              const SizedBox(width: 10),
              Expanded(flex: 4, child: CustomPaint(painter: Sparkline(_history[id] ?? const [], s.min, s.max, c, p.border))),
            ])
          : Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Expanded(child: Text(s.name(lang), maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 13, color: p.textDim))),
          Text(_fmt(s, _values[id]), style: display(context, 18, w: FontWeight.w700)),
          const SizedBox(width: 5),
          Text(unitFor(s, t, lang), style: TextStyle(fontSize: 11, color: p.textDim)),
        ]),
        const SizedBox(height: 4),
        Expanded(child: CustomPaint(painter: Sparkline(_history[id] ?? const [], s.min, s.max, c, p.border))),
      ]),
    );
  }
}

/// Единицы на языке интерфейса.
String unitFor(Sensor s, AppLocalizations t, String lang) {
  switch (s.unit) {
    case 'rpm':
      return t.rpmUnit;
    case 'V':
      return t.voltUnit;
    case 'km/h':
      return lang == 'en' ? 'km/h' : 'км/ч';
    case 'kPa':
      return lang == 'en' ? 'kPa' : 'кПа';
    case 'g/s':
      return lang == 'en' ? 'g/s' : 'г/с';
    default:
      return s.unit;
  }
}
