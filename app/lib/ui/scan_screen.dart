import 'package:flutter/material.dart';

import '../kb/knowledge_base.dart';
import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../state/app_state.dart';
import '../state/diag_service.dart';
import '../state/scan_store.dart';
import '../theme.dart';
import 'discovery_screen.dart';
import 'ecu_detail_screen.dart';
import 'report.dart';
import 'widgets.dart';

/// «Блоки»: сохранённый скан текущей машины (последний или выбранный в истории).
/// Сам не сканирует: новый опрос — кнопкой «Автоскан» на главном или «обновить» здесь.
class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});
  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  late final AppState _app; // в dispose() к context уже не обратиться
  List<EcuResult> get _results => _app.scanResults;
  bool _running = false;
  bool _reporting = false;
  String? _error;

  Future<void> _report(SavedScan scan) async {
    final app = AppScope.read(context);
    final t = AppLocalizations.of(context);
    setState(() => _reporting = true);
    try {
      await ScanReport.share(app, t, scan);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t.error('$e'))));
    } finally {
      if (mounted) setState(() => _reporting = false);
    }
  }

  @override
  void initState() {
    super.initState();
    _app = AppScope.read(context);
    if (_app.scanRequested) {
      _app.scanRequested = false;
      _scan();
    }
  }

  @override
  void dispose() {
    // ушли со вкладки посреди скана — неполный итог не сохраняем
    if (_running) _app.scanResults = [];
    super.dispose();
  }

  Future<void> _scan() async {
    final app = AppScope.read(context);
    final diag = app.diag;
    if (diag == null) return;
    setState(() {
      app.scanResults = [];
      _running = true;
      _error = null;
    });
    try {
      final started = DateTime.now();
      await for (final r in diag.autoScan()) {
        if (!mounted) return;
        setState(() => _results.add(r));
      }
      final answered = _results.where((r) => r.answered).toList();
      // никто не ответил — адаптер не в машине или зажигание выключено: в историю не пишем
      if (answered.isEmpty) {
        app.scanResults = [];
        if (mounted) setState(() => _error = AppLocalizations.of(context).scanNobody);
        return;
      }
      // сначала VIN: по нему гараж выбирает (или заводит) машину, потом пишем скан ей
      final vin = await diag.carVin(answered);
      if (vin != null) await app.setVin(vin);
      await app.saveScan(SavedScan(
        id: started.millisecondsSinceEpoch.toString(),
        time: started,
        vin: vin ?? app.vin,
        batteryMv: app.batteryMv,
        fw: app.fw,
        ecus: [for (final r in _results) r.saved()],
      ));
      app.scanResults = [];
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  Future<void> _history() async {
    final app = AppScope.read(context);
    final t = AppLocalizations.of(context);
    final id = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (c) {
        final p = c.p;
        final lang = app.lang;
        return SafeArea(
          child: ListView(shrinkWrap: true, children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
              child: Text(t.scanHistory, style: display(c, 17, w: FontWeight.w700)),
            ),
            for (final s in app.scans)
              ListTile(
                selected: s == app.shownScan,
                leading: Icon(s.module == null ? Icons.radar : Icons.refresh, color: s.faults > 0 ? p.bad : p.good),
                title: Text(stamp(s.time), style: mono(c, 15)),
                subtitle: Text('${s.module == null ? t.autoScan : t.scanModule(_nodeName(app.kb, s.module!, lang))}'
                    ' · ${t.faultCount(s.faults)} · ${t.modules}: ${s.answered.length}'),
                onTap: () => Navigator.pop(c, s.id),
              ),
          ]),
        );
      },
    );
    if (id != null) app.viewScan(id);
  }

  String _nodeName(KnowledgeBase? kb, String node, String lang) =>
      kb?.ecus.where((e) => e.node == node).firstOrNull?.nameFor(lang) ?? node;

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final app = AppScope.of(context);
    final kb = app.kb;
    final total = kb?.ecus.length ?? 0;
    final scan = _running ? null : app.shownScan;
    // идущий скан показываем по мере опроса; иначе — сохранённый
    final ecus = _running ? [for (final r in _results) r.saved()] : scan?.ecus ?? const <SavedEcu>[];
    final answered = ecus.where((e) => e.answered).toList();
    final bad = answered.where((e) => e.dtcs.isNotEmpty).length;
    final canScan = app.live && !_running;

    final String title;
    if (_running) {
      title = t.scanning;
    } else if (scan == null) {
      title = t.noScans;
    } else {
      title = t.scanAt(stamp(scan.time));
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(t.navModules),
        backgroundColor: p.bg,
        actions: [
          IconButton(
            tooltip: t.scanHistory,
            onPressed: _running || app.scans.isEmpty ? null : _history,
            icon: const Icon(Icons.history),
          ),
          IconButton(
            tooltip: t.report,
            onPressed: (scan == null || _reporting) ? null : () => _report(scan),
            icon: _reporting
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.ios_share),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
        children: [
          GlowCard(
            tint: p.info,
            padding: const EdgeInsets.all(14),
            child: Row(children: [
              SizedBox(
                width: 68,
                height: 68,
                child: Stack(alignment: Alignment.center, children: [
                  SizedBox.expand(
                    child: CircularProgressIndicator(
                      value: total == 0 ? 0 : (_running ? _results.length : ecus.isEmpty ? 0 : total) / total,
                      strokeWidth: 7,
                      backgroundColor: p.border,
                      color: p.accent,
                      strokeCap: StrokeCap.round,
                    ),
                  ),
                  // пока идёт скан — сколько мест проверено; потом — сколько блоков нашлось
                  if (_running)
                    Text('${_results.length}/$total', style: display(context, 16))
                  else
                    Column(mainAxisSize: MainAxisSize.min, children: [
                      Text(scan == null ? '—' : '${answered.length}', style: display(context, 22, w: FontWeight.w700)),
                      Text(t.ofTotal(total), style: TextStyle(fontSize: 10, height: 1, color: p.textDim)),
                    ]),
                ]),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(title, style: display(context, 17, w: FontWeight.w700)),
                  const SizedBox(height: 4),
                  if (_running || scan != null)
                    Text('${t.scanFound(answered.length, total)} · ${t.scanSummary(answered.length - bad, bad)}',
                        style: TextStyle(color: p.textDim))
                  else
                    Text(app.live ? t.noScansHint : t.needAdapterScan, style: TextStyle(color: p.textDim)),
                  if (scan?.module != null)
                    Text(t.scanModule(_nodeName(kb, scan!.module!, app.lang)), style: TextStyle(fontSize: 12, color: p.textDim)),
                ]),
              ),
              if (app.live)
                IconButton(
                  tooltip: t.rescan,
                  onPressed: canScan ? _scan : null,
                  icon: Icon(Icons.refresh, color: canScan ? p.accent : p.textDim),
                ),
            ]),
          ),
          if (app.viewingOld && !_running)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Row(children: [
                Icon(Icons.history, size: 18, color: p.textDim),
                const SizedBox(width: 8),
                Expanded(child: Text(t.scanOlder, style: TextStyle(color: p.textDim))),
                TextButton(onPressed: () => app.viewScan(null), child: Text(t.scanLatest)),
              ]),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 16),
              child: Text(_error == t.scanNobody ? _error! : t.error(_error!), style: TextStyle(color: p.bad)),
            ),
          if (scan == null && !_running && app.live)
            Padding(
              padding: const EdgeInsets.only(top: 16),
              child: GradientButton(
                icon: Icons.radar,
                label: t.autoScan,
                colors: const [Color(0xFF0E7490), Color(0xFF6D28D9)],
                onPressed: _scan,
              ),
            ),
          const SizedBox(height: 14),
          // необязательные блоки (их может не быть на этой машине) показываем, только если ответили
          for (final e in ecus)
            if (kb?.ecus.where((d) => d.tx == e.tx).firstOrNull case final def? when e.answered || !def.optional) ...[
              _tile(context, def, e, t),
              const SizedBox(height: 8),
            ],
          if (app.live) ...[
            const SizedBox(height: 8),
            GlowCard(
              tint: p.accent,
              onTap: _running ? null : () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const DiscoveryScreen())),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              child: Row(children: [
                Icon(Icons.travel_explore, color: p.accent),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(t.discover, style: TextStyle(fontWeight: FontWeight.w600, color: p.text)),
                    Text(t.discoverHint, style: TextStyle(fontSize: 12, color: p.textDim)),
                  ]),
                ),
                Icon(Icons.chevron_right, color: p.textDim),
              ]),
            ),
          ],
        ],
      ),
    );
  }

  Widget _tile(BuildContext context, EcuDef def, SavedEcu e, AppLocalizations t) {
    final p = context.p;
    final lang = AppScope.of(context).lang;
    final (icon, tint) = ecuLook(def);
    final Widget trailing;
    if (!e.answered) {
      trailing = Text(t.noAnswer, style: TextStyle(fontSize: 13, color: p.textDim));
    } else if (e.dtcs.isNotEmpty) {
      trailing = Pill(e.dtcs.length.toString(), fg: Colors.white, bg: p.bad);
    } else {
      trailing = Container(width: 10, height: 10, margin: const EdgeInsets.only(right: 6), decoration: BoxDecoration(color: p.good, shape: BoxShape.circle));
    }
    return GlowCard(
      tint: e.dtcs.isNotEmpty ? p.bad : p.border,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      onTap: e.answered && !_running ? () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => EcuDetailScreen(def))) : null,
      child: Row(children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(color: tint.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(12)),
          child: Icon(icon, color: e.answered ? tint : p.textDim, size: 24),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(def.nameFor(lang), style: TextStyle(fontWeight: FontWeight.w600, color: p.text)),
            Text(
                '${def.tx.toRadixString(16).toUpperCase()} → ${def.rx.toRadixString(16).toUpperCase()}'
                '${e.model != null ? ' · ${e.model}' : ''}',
                style: mono(context, 12, color: p.textDim)),
          ]),
        ),
        const SizedBox(width: 8),
        trailing,
      ]),
    );
  }
}

/// Значок и цвет блока по его типу из базы знаний (поле "icon").
(IconData, Color) ecuLook(EcuDef e) {
  switch (e.icon) {
    case 'bsi':
      return (Icons.memory, const Color(0xFF8B5CF6));
    case 'engine':
      return (Icons.settings_suggest, const Color(0xFFF59E0B));
    case 'abs':
      return (Icons.album_outlined, const Color(0xFF06B6D4));
    case 'airbag':
      return (Icons.airline_seat_recline_normal, const Color(0xFFEAB308));
    case 'cluster':
      return (Icons.speed, const Color(0xFF22C55E));
    case 'climate':
      return (Icons.ac_unit, const Color(0xFF38BDF8));
    case 'steering':
      return (Icons.trip_origin, const Color(0xFF94A3B8));
    case 'gearbox':
      return (Icons.alt_route, const Color(0xFFF97316));
    case 'radio':
      return (Icons.radio, const Color(0xFFEC4899));
    case 'parking':
      return (Icons.sensors, const Color(0xFF14B8A6));
    case 'alarm':
      return (Icons.shield_outlined, const Color(0xFFEF4444));
    case 'power':
      return (Icons.battery_charging_full, const Color(0xFF84CC16));
    default:
      return (Icons.developer_board, const Color(0xFF94A3B8));
  }
}
