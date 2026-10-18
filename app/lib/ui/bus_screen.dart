import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Монитор шины: только слушаем. Режим summary — последний кадр каждого ID.
class BusScreen extends StatefulWidget {
  const BusScreen({super.key});
  @override
  State<BusScreen> createState() => _BusScreenState();
}

class _BusScreenState extends State<BusScreen> {
  StreamSubscription? _sub;
  final _frames = <String, Map<String, dynamic>>{};
  bool _paused = false;
  String _bus = 'B';
  late final AppState _app; // берём один раз: в dispose() искать по дереву уже нельзя

  @override
  void initState() {
    super.initState();
    _app = AppScope.read(context);
    _start();
  }

  Future<void> _start() async {
    final app = _app;
    try {
      await app.client.openBus(_bus, listen: true);
      await app.client.monitor(_bus, mode: 'summary');
      _sub = app.client.events.listen((ev) {
        if (_paused || ev['ev'] != 'frames' || ev['bus'] != _bus) return;
        for (final f in (ev['frames'] as List)) {
          _frames[f['id'] as String] = f as Map<String, dynamic>;
        }
        if (mounted) setState(() {});
      });
    } catch (_) {}
  }

  Future<void> _switchBus(String b) async {
    final app = _app;
    await app.client.monitorStop(_bus);
    await app.client.closeBus(_bus);
    setState(() {
      _bus = b;
      _frames.clear();
    });
    await _sub?.cancel();
    await _start();
  }

  /// «0E00000F» -> «0E 00 00 0F»: байты читать легче.
  static String _spaced(String hex) => [
        for (var i = 0; i < hex.length; i += 2) hex.substring(i, i + 2 > hex.length ? hex.length : i + 2)
      ].join(' ');

  @override
  void dispose() {
    final app = _app;
    _sub?.cancel();
    app.client.monitorStop(_bus);
    app.client.closeBus(_bus);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final ids = _frames.keys.toList()..sort();
    return Scaffold(
      appBar: AppBar(
        backgroundColor: p.bg,
        title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(t.busMonitor, style: TextStyle(fontSize: 18, color: p.text)),
          Text(t.busMonitorSub, style: TextStyle(fontSize: 12, color: p.good)),
        ]),
        actions: [
          IconButton(
            icon: Icon(_paused ? Icons.play_arrow : Icons.pause),
            onPressed: () => setState(() => _paused = !_paused),
          ),
        ],
      ),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
          child: SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'A', label: Text('CAN-A · 6/14')),
              ButtonSegment(value: 'B', label: Text('CAN-B · 3/8')),
            ],
            selected: {_bus},
            onSelectionChanged: (s) => _switchBus(s.first),
            style: SegmentedButton.styleFrom(
              selectedBackgroundColor: p.accent,
              selectedForegroundColor: p.onAccent,
              foregroundColor: p.textDim,
              side: BorderSide(color: p.border),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
          child: Row(children: [
            SizedBox(width: 60, child: Text('ID', style: TextStyle(fontSize: 12, color: p.textDim))),
            SizedBox(width: 44, child: Text(t.hz, style: TextStyle(fontSize: 12, color: p.textDim))),
            Expanded(child: Text(t.dataCol, style: TextStyle(fontSize: 12, color: p.textDim))),
          ]),
        ),
        Divider(height: 1, color: p.border),
        Expanded(
          child: ListView.builder(
            itemCount: ids.length,
            itemBuilder: (_, i) {
              final f = _frames[ids[i]]!;
              return Container(
                height: 40,
                padding: const EdgeInsets.symmetric(horizontal: 20),
                decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.border.withValues(alpha: 0.5)))),
                child: Row(children: [
                  SizedBox(width: 60, child: Text(ids[i], style: mono(context, 13, color: p.accent))),
                  SizedBox(width: 44, child: Text('${f['hz'] ?? '—'}', style: mono(context, 13, color: p.textDim))),
                  Expanded(child: Text(_spaced('${f['data']}'), overflow: TextOverflow.ellipsis, style: mono(context, 13))),
                ]),
              );
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
          child: Align(alignment: Alignment.centerLeft, child: Text(t.frameRate(ids.length), style: mono(context, 13, color: p.textDim))),
        ),
      ]),
    );
  }
}
