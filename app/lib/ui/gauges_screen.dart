import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../kb/sensors.dart';
import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../transport/uds.dart';
import 'widgets.dart';

/// Живые данные: один большой прибор сверху и четыре маленьких снизу.
/// Нажатие на прибор — выбрать, какой датчик на этом месте. Режим «Графики» —
/// те же пять датчиков линиями за последнюю минуту.
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
  bool _graphs = false;
  Set<int>? _supported;
  final _values = <String, double>{};
  final _history = <String, List<double>>{};

  // запись лога в CSV
  DateTime? _recStart;
  List<String> _recIds = [];
  final _rows = <String>[];
  bool get _recording => _recStart != null;

  void _startRec() {
    final t = AppLocalizations.of(context);
    _recIds = List.of(_app.gaugeSlots.toSet());
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

  /// Опрашиваем только то, что сейчас на экране.
  Future<void> _tick() async {
    final o = _obd;
    if (o == null || _busy) return;
    _busy = true;
    try {
      for (final id in {..._app.gaugeSlots, ..._recIds}) {
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

  Future<void> _pick(int slot) async {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final lang = _app.lang;
    final current = _app.gaugeSlots[slot];
    final chosen = await showModalBottomSheet<String>(
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
    if (chosen != null) _app.setGaugeSlot(slot, chosen);
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final p = context.p;
    AppScope.of(context); // перестраиваться при смене датчиков/языка
    final slots = _app.gaugeSlots;

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
          : ListView(
              padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
              children: [
                _modeSwitch(context, t),
                const SizedBox(height: 14),
                if (!_graphs) ...[
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
                ] else
                  for (var i = 0; i < 5; i++) ...[
                    _graphCard(context, i, slots[i]),
                    const SizedBox(height: 10),
                  ],
                const SizedBox(height: 4),
                Row(children: [
                  Icon(Icons.touch_app_outlined, size: 18, color: p.textDim),
                  const SizedBox(width: 8),
                  Expanded(child: Text(t.gaugesHint, style: TextStyle(fontSize: 13, color: p.textDim))),
                ]),
              ],
            ),
    );
  }

  Widget _modeSwitch(BuildContext context, AppLocalizations t) {
    final p = context.p;
    Widget seg(String label, bool on, VoidCallback tap) => Expanded(
          child: GestureDetector(
            onTap: tap,
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
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(color: p.surface, borderRadius: BorderRadius.circular(16), border: Border.all(color: p.border)),
      child: Row(children: [
        seg(t.arrows, !_graphs, () => setState(() => _graphs = false)),
        seg(t.graphs, _graphs, () => setState(() => _graphs = true)),
      ]),
    );
  }

  Widget _bigGauge(BuildContext context, String id) {
    final t = AppLocalizations.of(context);
    final s = sensorById(id);
    final lang = _app.lang;
    final p = context.p;
    return GlowCard(
      tint: p.gaugeA,
      onTap: () => _pick(0),
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

  static const _smallColors = [Color(0xFFF59E0B), Color(0xFF22C55E), Color(0xFF8B5CF6), Color(0xFF06B6D4)];

  Widget _smallGauge(BuildContext context, int slot, String id) {
    final t = AppLocalizations.of(context);
    final s = sensorById(id);
    final lang = _app.lang;
    final c = _smallColors[(slot - 1) % _smallColors.length];
    return GlowCard(
      tint: c,
      onTap: () => _pick(slot),
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

  Widget _graphCard(BuildContext context, int slot, String id) {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final s = sensorById(id);
    final lang = _app.lang;
    final c = slot == 0 ? p.gaugeA : _smallColors[(slot - 1) % _smallColors.length];
    final v = _values[id];
    return GlowCard(
      tint: c,
      onTap: () => _pick(slot),
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Expanded(child: Text(s.name(lang), style: TextStyle(fontSize: 14, color: p.textDim))),
          Text(
            v == null || v.isNaN ? '—' : v.toStringAsFixed(s.decimals).replaceAll('.', ','),
            style: display(context, 22, w: FontWeight.w700),
          ),
          const SizedBox(width: 6),
          Text(unitFor(s, t, lang), style: TextStyle(fontSize: 12, color: p.textDim)),
        ]),
        const SizedBox(height: 6),
        SizedBox(
          height: slot == 0 ? 90 : 56,
          child: CustomPaint(painter: Sparkline(_history[id] ?? const [], s.min, s.max, c, p.border)),
        ),
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
