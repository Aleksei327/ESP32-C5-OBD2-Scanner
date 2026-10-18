import 'package:flutter/material.dart';

import '../kb/knowledge_base.dart';
import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../state/diag_service.dart';
import '../theme.dart';
import 'discovery_screen.dart';
import 'ecu_detail_screen.dart';
import 'report.dart';
import 'widgets.dart';

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});
  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  final _results = <EcuResult>[];
  bool _running = false;
  bool _reporting = false;

  Future<void> _report() async {
    final app = AppScope.read(context);
    final t = AppLocalizations.of(context);
    setState(() => _reporting = true);
    try {
      await ScanReport.share(app, t, List.of(_results));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t.error('$e'))));
    } finally {
      if (mounted) setState(() => _reporting = false);
    }
  }
  String? _error;

  @override
  void initState() {
    super.initState();
    _scan();
  }

  Future<void> _scan() async {
    final app = AppScope.read(context);
    final diag = app.diag;
    if (diag == null) return;
    setState(() {
      _results.clear();
      _running = true;
      _error = null;
    });
    try {
      await for (final r in diag.autoScan()) {
        if (!mounted) return;
        setState(() => _results.add(r));
      }
      final answered = _results.where((r) => r.answered).toList();
      // сначала VIN: по нему гараж выбирает (или заводит) машину, потом пишем ей итог
      if (answered.isNotEmpty) {
        final id = await diag.identify(answered.first.def);
        if (id['vin'] != null && id['vin']!.isNotEmpty) app.setVin(id['vin']!);
      }
      app.setScanResult(
        faults: answered.fold(0, (n, r) => n + r.dtcs.length),
        answered: answered.length,
      );
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final total = AppScope.of(context).kb?.ecus.length ?? 0;
    final answered = _results.where((r) => r.answered).toList();
    final bad = answered.where((r) => r.dtcs.isNotEmpty).length;

    return Scaffold(
      appBar: AppBar(title: Text(t.autoScan), backgroundColor: p.bg),
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
                      value: total == 0 ? 0 : _results.length / total,
                      strokeWidth: 7,
                      backgroundColor: p.border,
                      color: p.accent,
                      strokeCap: StrokeCap.round,
                    ),
                  ),
                  Text('${_results.length}/$total', style: display(context, 16)),
                ]),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(_running ? t.scanning : t.scanDone, style: display(context, 18, w: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text(t.scanSummary(answered.length - bad, bad), style: TextStyle(color: p.textDim)),
                ]),
              ),
              IconButton(
                tooltip: t.report,
                onPressed: (_running || _reporting || _results.isEmpty) ? null : _report,
                icon: _reporting
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                    : Icon(Icons.ios_share, color: p.accent),
              ),
              IconButton(
                tooltip: t.rescan,
                onPressed: _running ? null : _scan,
                icon: Icon(Icons.refresh, color: p.accent),
              ),
            ]),
          ),
          if (_error != null)
            Padding(padding: const EdgeInsets.only(top: 16), child: Text(t.error(_error!), style: TextStyle(color: p.bad))),
          const SizedBox(height: 14),
          for (final r in _results) ...[
            _tile(context, r, t),
            const SizedBox(height: 8),
          ],
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
      ),
    );
  }

  Widget _tile(BuildContext context, EcuResult r, AppLocalizations t) {
    final p = context.p;
    final lang = AppScope.of(context).lang;
    final (icon, tint) = ecuLook(r.def);
    final Widget trailing;
    if (!r.answered) {
      trailing = Text(t.noAnswer, style: TextStyle(fontSize: 13, color: p.textDim));
    } else if (r.dtcs.isNotEmpty) {
      trailing = Pill(r.dtcs.length.toString(), fg: Colors.white, bg: p.bad);
    } else {
      trailing = Container(width: 10, height: 10, margin: const EdgeInsets.only(right: 6), decoration: BoxDecoration(color: p.good, shape: BoxShape.circle));
    }
    return GlowCard(
      tint: r.dtcs.isNotEmpty ? p.bad : p.border,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      onTap: r.answered ? () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => EcuDetailScreen(r.def))) : null,
      child: Row(children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(color: tint.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(12)),
          child: Icon(icon, color: r.answered ? tint : p.textDim, size: 24),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(r.def.nameFor(lang), style: TextStyle(fontWeight: FontWeight.w600, color: p.text)),
            Text('${r.def.tx.toRadixString(16).toUpperCase()} → ${r.def.rx.toRadixString(16).toUpperCase()}',
                style: mono(context, 12, color: p.textDim)),
          ]),
        ),
        trailing,
      ]),
    );
  }
}

/// Значок и цвет блока по его типу из базы знаний (поле "icon").
(IconData, Color) ecuLook(EcuDef e) {
  switch (e.m['icon']) {
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
    default:
      return (Icons.developer_board, const Color(0xFF94A3B8));
  }
}
