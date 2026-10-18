import 'package:flutter/material.dart';

import '../kb/knowledge_base.dart';
import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../theme.dart';
import '../transport/uds.dart';
import 'widgets.dart';

/// Блок: вкладки Инфо / Ошибки / Данные / Конфиг. Опрос — через DiagService.
class EcuDetailScreen extends StatefulWidget {
  const EcuDetailScreen(this.def, {super.key});
  final EcuDef def;
  @override
  State<EcuDetailScreen> createState() => _EcuDetailScreenState();
}

class _EcuDetailScreenState extends State<EcuDetailScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs;

  @override
  void initState() {
    super.initState();
    final n = widget.def.config.isNotEmpty ? 4 : 3;
    _tabs = TabController(length: n, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final lang = AppScope.of(context).lang;
    final hasCfg = widget.def.config.isNotEmpty;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: p.bg,
        title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(widget.def.nameFor(lang), style: TextStyle(fontSize: 18, color: p.text)),
          Text('${widget.def.tx.toRadixString(16).toUpperCase()} → ${widget.def.rx.toRadixString(16).toUpperCase()}',
              style: mono(context, 12, color: p.textDim)),
        ]),
        bottom: FolderTabs(
          controller: _tabs,
          tabs: [
            FolderTab(t.info, Icons.info_outline_rounded, const Color(0xFF2F7BF6)),
            FolderTab(t.faults, Icons.warning_amber_rounded, const Color(0xFFE11D48)),
            FolderTab(t.navGauges, Icons.speed_rounded, const Color(0xFFF59E0B)),
            if (hasCfg) FolderTab(t.configTab, Icons.tune_rounded, const Color(0xFF8B5CF6)),
          ],
        ),
      ),
      // SafeArea снизу: кнопки не должны уходить под системную панель Android
      body: SafeArea(top: false, child: TabBarView(controller: _tabs, children: [
        _IdentTab(widget.def),
        _FaultsTab(widget.def),
        _LiveTab(widget.def),
        if (hasCfg) _ConfigTab(widget.def),
      ])),
    );
  }
}

class _IdentTab extends StatefulWidget {
  const _IdentTab(this.def);
  final EcuDef def;
  @override
  State<_IdentTab> createState() => _IdentTabState();
}

class _IdentTabState extends State<_IdentTab> {
  Map<String, String>? _d;
  @override
  void initState() {
    super.initState();
    AppScope.read(context).diag?.identify(widget.def).then((v) => mounted ? setState(() => _d = v) : null);
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    if (_d == null) return const Center(child: CircularProgressIndicator());
    final rows = [
      if (_d!['vin'] != null) (t.vin, _d!['vin']!),
      if (_d!['part'] != null) (t.partNumber, _d!['part']!),
      if (_d!['sw'] != null) (t.software, _d!['sw']!),
    ];
    return ListView(padding: const EdgeInsets.all(20), children: [
      GlowCard(
        tint: context.p.border,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(
          children: [
            for (final (k, v) in rows)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Row(children: [
                  Text(k, style: TextStyle(color: context.p.textDim)),
                  const SizedBox(width: 16),
                  Expanded(child: FittedBox(fit: BoxFit.scaleDown, alignment: Alignment.centerRight, child: Text(v, maxLines: 1, style: mono(context, 14)))),
                ]),
              ),
          ],
        ),
      ),
    ]);
  }
}

class _FaultsTab extends StatefulWidget {
  const _FaultsTab(this.def);
  final EcuDef def;
  @override
  State<_FaultsTab> createState() => _FaultsTabState();
}

class _FaultsTabState extends State<_FaultsTab> {
  List<Dtc>? _dtcs;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final d = await AppScope.read(context).diag?.readFaults(widget.def);
    if (mounted) setState(() => _dtcs = d ?? []);
  }

  Future<void> _clear() async {
    final t = AppLocalizations.of(context);
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        content: Text(t.clearConfirm),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: Text(t.cancel)),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: Text(t.clear)),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    final diag = AppScope.read(context).diag;
    setState(() => _busy = true);
    try {
      await diag?.clearFaults(widget.def);
      await _load();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Какая ошибка раскрыта и её стоп-кадр (null — ещё грузится).
  String? _open;
  List<(LiveItem, double)>? _snap;
  bool _snapFailed = false;

  Future<void> _toggle(Dtc d) async {
    if (_open == d.code) {
      setState(() => _open = null);
      return;
    }
    setState(() {
      _open = d.code;
      _snap = null;
      _snapFailed = false;
    });
    final diag = AppScope.read(context).diag;
    try {
      final s = await diag!.readSnapshot(widget.def, d);
      if (mounted && _open == d.code) setState(() => _snap = s);
    } catch (_) {
      if (mounted && _open == d.code) setState(() => _snapFailed = true);
    }
  }

  List<Widget> _snapshotView(BuildContext context, AppLocalizations t, String lang) {
    final p = context.p;
    final head = Padding(
      padding: const EdgeInsets.only(top: 14, bottom: 8),
      child: Text(t.freezeFrame.toUpperCase(),
          style: TextStyle(fontSize: 11, letterSpacing: 0.6, fontWeight: FontWeight.w600, color: p.textDim)),
    );
    if (_snapFailed || (_snap != null && _snap!.isEmpty)) {
      return [head, Text(t.noFreezeFrame, style: TextStyle(color: p.textDim))];
    }
    if (_snap == null) {
      return [head, const LinearProgressIndicator(minHeight: 2)];
    }
    return [
      head,
      // ячейки по половине ширины, высота — по содержимому (без обрезания цифр)
      LayoutBuilder(
        builder: (context, box) => Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final (item, v) in _snap!)
              Container(
                width: (box.maxWidth - 8) / 2,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(color: p.bg, borderRadius: BorderRadius.circular(12)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${item.nameFor(lang)} · ${liveUnit(item.unit, t, lang)}',
                      maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, color: p.textDim)),
                  Text(v.toStringAsFixed(item.decimals).replaceAll('.', ','), style: display(context, 18, w: FontWeight.w700)),
                ]),
              ),
          ],
        ),
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final app = AppScope.of(context);
    if (_dtcs == null) return const Center(child: CircularProgressIndicator());
    if (_dtcs!.isEmpty) {
      return Center(child: Text(t.noFaults, style: TextStyle(color: p.textDim)));
    }
    return Column(children: [
      Expanded(
        child: ListView.separated(
          padding: const EdgeInsets.all(20),
          itemCount: _dtcs!.length,
          separatorBuilder: (_, _) => const SizedBox(height: 10),
          itemBuilder: (_, i) {
            final d = _dtcs![i];
            final text = app.kb?.dtcText(d.code, app.lang) ?? t.unknownFault;
            final open = _open == d.code;
            return GlowCard(
              tint: d.active ? p.bad : p.border,
              onTap: () => _toggle(d),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Text(d.code, style: mono(context, 16).copyWith(fontWeight: FontWeight.w600)),
                  const Spacer(),
                  Pill(d.active ? t.faultActive : t.faultStored,
                      fg: d.active ? Colors.white : p.textDim,
                      bg: d.active ? p.bad : p.textDim.withValues(alpha: 0.12)),
                  Icon(open ? Icons.expand_less : Icons.expand_more, color: p.textDim),
                ]),
                const SizedBox(height: 6),
                Text(text, style: TextStyle(color: p.text)),
                if (open) ..._snapshotView(context, t, app.lang),
              ]),
            );
          },
        ),
      ),
      Padding(
        padding: const EdgeInsets.all(20),
        child: GradientButton(
          icon: Icons.delete_sweep_rounded,
          label: t.clearFaults,
          colors: const [Color(0xFFE11D48), Color(0xFFF97316)],
          busy: _busy,
          onPressed: _clear,
        ),
      ),
    ]);
  }
}

class _LiveTab extends StatefulWidget {
  const _LiveTab(this.def);
  final EcuDef def;
  @override
  State<_LiveTab> createState() => _LiveTabState();
}

class _LiveTabState extends State<_LiveTab> {
  List<double> _vals = [];
  bool _run = true;

  @override
  void initState() {
    super.initState();
    _poll();
  }

  Future<void> _poll() async {
    final diag = AppScope.read(context).diag;
    while (_run && mounted && diag != null && widget.def.live.isNotEmpty) {
      final v = await diag.readLive(widget.def);
      if (!mounted) return;
      setState(() => _vals = v);
      await Future.delayed(const Duration(milliseconds: 300));
    }
  }

  @override
  void dispose() {
    _run = false;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final lang = AppScope.of(context).lang;
    final p = context.p;
    if (widget.def.live.isEmpty) {
      return Center(child: Text('—', style: TextStyle(color: p.textDim)));
    }
    final t = AppLocalizations.of(context);
    return GridView.count(
      padding: const EdgeInsets.all(20),
      crossAxisCount: 2,
      mainAxisSpacing: 12,
      crossAxisSpacing: 12,
      childAspectRatio: 1.6,
      children: [
        for (var i = 0; i < widget.def.live.length; i++)
          GlowCard(
            tint: p.info,
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              // сверху: что и в чём меряем — «Обороты · об/мин»
              Text(
                '${widget.def.live[i].nameFor(lang)} · ${liveUnit(widget.def.live[i].unit, t, lang)}',
                maxLines: 2,
                style: TextStyle(fontSize: 13, height: 1.25, color: p.textDim),
              ),
              const Spacer(),
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(
                  i < _vals.length && !_vals[i].isNaN
                      ? _vals[i].toStringAsFixed(widget.def.live[i].decimals).replaceAll('.', ',')
                      : '—',
                  style: display(context, 28, w: FontWeight.w700),
                ),
              ),
            ]),
          ),
      ],
    );
  }
}

/// Единица из базы знаний — на языке интерфейса.
String liveUnit(String unit, AppLocalizations t, String lang) {
  switch (unit) {
    case 'rpm':
      return t.rpmUnit;
    case 'V':
      return t.voltUnit;
    case 'mV':
      return lang == 'en' ? 'mV' : 'мВ';
    case 'km/h':
      return lang == 'en' ? 'km/h' : 'км/ч';
    default:
      return unit;
  }
}

/// Настройки блока — только просмотр. Запись в приложении не делаем.
class _ConfigTab extends StatefulWidget {
  const _ConfigTab(this.def);
  final EcuDef def;
  @override
  State<_ConfigTab> createState() => _ConfigTabState();
}

class _ConfigTabState extends State<_ConfigTab> {
  Map<int, int>? _vals;

  @override
  void initState() {
    super.initState();
    AppScope.read(context).diag?.readConfig(widget.def).then((v) {
      if (!mounted) return;
      setState(() => _vals = v);
    });
  }

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final lang = AppScope.of(context).lang;
    if (_vals == null) return const Center(child: CircularProgressIndicator());
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        GlowCard(
          tint: p.border,
          padding: EdgeInsets.zero,
          child: Column(children: [
            for (final c in widget.def.config)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.border))),
                child: Row(children: [
                  Expanded(child: Text(c.nameFor(lang), style: TextStyle(color: p.text))),
                  Text(_show(c.type, _vals![c.did]), style: mono(context, 14, color: p.textDim)),
                ]),
              ),
          ]),
        ),
      ],
    );
  }

  String _show(String type, int? v) {
    if (v == null) return '—';
    if (type == 'bool') return v == 1 ? 'ON' : 'OFF';
    return '$v';
  }
}
