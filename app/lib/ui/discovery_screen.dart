import 'dart:async';

import 'package:flutter/material.dart';

import '../kb/knowledge_base.dart';
import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../state/diag_service.dart';
import '../theme.dart';
import 'scan_screen.dart' show ecuLook;
import 'widgets.dart';

/// Поиск блоков: перебор всех адресов на шине 3/8. Показывает, кто ответил,
/// и есть ли такой блок в базе знаний. На живой машине так узнаём полный список.
class DiscoveryScreen extends StatefulWidget {
  const DiscoveryScreen({super.key});
  @override
  State<DiscoveryScreen> createState() => _DiscoveryScreenState();
}

class _DiscoveryScreenState extends State<DiscoveryScreen> {
  StreamSubscription<DiscoveryStep>? _sub;
  DiscoveryStep? _step;
  bool _done = false;

  @override
  void initState() {
    super.initState();
    final diag = AppScope.read(context).diag;
    if (diag == null) return;
    _sub = diag.discover().listen(
      (s) => setState(() => _step = s),
      onDone: () => setState(() => _done = true),
      onError: (_) => setState(() => _done = true),
    );
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final app = AppScope.of(context);
    final s = _step;
    final known = {for (final e in app.kb?.ecus ?? const <EcuDef>[]) e.tx: e};
    return Scaffold(
      appBar: AppBar(backgroundColor: p.bg, title: Text(t.discover)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
        children: [
          GlowCard(
            tint: p.info,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(_done ? t.discoverDone : t.discoverSub, style: display(context, 17, w: FontWeight.w700)),
              const SizedBox(height: 10),
              LinearProgressIndicator(
                value: s == null ? null : s.done / s.total,
                minHeight: 6,
                borderRadius: BorderRadius.circular(3),
                backgroundColor: p.border,
                color: p.accent,
              ),
              const SizedBox(height: 8),
              Text(
                s == null ? '…' : '${s.done}/${s.total} · ${t.discoverFound(s.found.length)}',
                style: mono(context, 13, color: p.textDim),
              ),
            ]),
          ),
          const SizedBox(height: 14),
          for (final (tx, rx) in s?.found ?? const <(int, int)>[]) ...[
            _row(context, t, tx, rx, known[tx]),
            const SizedBox(height: 8),
          ],
        ],
      ),
    );
  }

  Widget _row(BuildContext context, AppLocalizations t, int tx, int rx, EcuDef? def) {
    final p = context.p;
    final lang = AppScope.of(context).lang;
    final (icon, tint) = def == null ? (Icons.help_outline, p.textDim) : ecuLook(def);
    return GlowCard(
      tint: def == null ? p.accent : p.border,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      child: Row(children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(color: tint.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(12)),
          child: Icon(icon, color: tint),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(def?.nameFor(lang) ?? t.unknownModule, style: TextStyle(fontWeight: FontWeight.w600, color: p.text)),
            Text('${tx.toRadixString(16).toUpperCase()} → ${rx.toRadixString(16).toUpperCase()}',
                style: mono(context, 12, color: p.textDim)),
          ]),
        ),
        Pill(def == null ? t.notInKb : t.inKb,
            fg: def == null ? p.accent : p.good,
            bg: (def == null ? p.accent : p.good).withValues(alpha: 0.12)),
      ]),
    );
  }
}
