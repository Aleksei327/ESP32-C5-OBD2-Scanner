import 'package:flutter/material.dart';

import '../kb/knowledge_base.dart';
import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../state/diag_service.dart';
import '../theme.dart';
import '../transport/diag.dart';
import 'widgets.dart';

/// Блок: вкладки Инфо / Ошибки / Данные / Опции. Опрос — через DiagService.
class EcuDetailScreen extends StatefulWidget {
  const EcuDetailScreen(this.def, {super.key});
  final EcuDef def;
  @override
  State<EcuDetailScreen> createState() => _EcuDetailScreenState();
}

class _EcuDetailScreenState extends State<EcuDetailScreen> with TickerProviderStateMixin {
  TabController? _tabs;

  bool _hasConfig(DiagService? d) => d != null && d.records(widget.def, 'config').isNotEmpty;

  /// Вкладок 3 или 4 (есть ли настройки), а это зависит от модели блока — она может смениться.
  void _syncTabs(int n) {
    if (_tabs?.length == n) return;
    final old = _tabs;
    _tabs = TabController(length: n, vsync: this, initialIndex: (old?.index ?? 0).clamp(0, n - 1));
    old?.dispose();
  }

  @override
  void dispose() {
    _tabs?.dispose();
    super.dispose();
  }

  Future<void> _chooseModel() async {
    final diag = AppScope.read(context).diag;
    if (diag == null) return;
    final lang = AppScope.read(context).lang;
    final t = AppLocalizations.of(context);
    final m = await showModalBottomSheet<EcuModel>(
      context: context,
      showDragHandle: true,
      builder: (c) => SafeArea(
        child: ListView(shrinkWrap: true, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
            child: Text(t.chooseModel, style: display(c, 17, w: FontWeight.w700)),
          ),
          for (final m in diag.modelChoices(widget.def))
            ListTile(
              title: Text(m.name, style: mono(c, 15)),
              subtitle: Text(m.titleFor(lang)),
              onTap: () => Navigator.pop(c, m),
            ),
        ]),
      ),
    );
    if (m == null || !mounted) return;
    diag.chooseModel(widget.def, m);
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final app = AppScope.of(context);
    final lang = app.lang;
    final diag = app.diag;
    final hasCfg = _hasConfig(diag);
    _syncTabs(hasCfg ? 4 : 3);
    final model = diag?.link(widget.def).model?.name ?? '';
    return Scaffold(
      appBar: AppBar(
        backgroundColor: p.bg,
        title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(widget.def.nameFor(lang), style: TextStyle(fontSize: 18, color: p.text)),
          Text(
              '${widget.def.tx.toRadixString(16).toUpperCase()} → ${widget.def.rx.toRadixString(16).toUpperCase()}'
              '${model.isEmpty ? '' : ' · $model'}',
              style: mono(context, 12, color: p.textDim)),
        ]),
        bottom: FolderTabs(
          controller: _tabs!,
          tabs: [
            FolderTab(t.info, Icons.info_outline_rounded, const Color(0xFF2F7BF6)),
            FolderTab(t.faults, Icons.warning_amber_rounded, const Color(0xFFE11D48)),
            FolderTab(t.dataCol, Icons.speed_rounded, const Color(0xFFF59E0B)),
            if (hasCfg) FolderTab(t.configTab, Icons.tune_rounded, const Color(0xFF8B5CF6)),
          ],
        ),
      ),
      // SafeArea снизу: кнопки не должны уходить под системную панель Android
      body: SafeArea(
        top: false,
        child: TabBarView(controller: _tabs, children: [
          _IdentTab(widget.def, onChoose: _chooseModel, key: ValueKey('i$model')),
          _FaultsTab(widget.def, key: ValueKey('f$model')),
          _LiveTab(widget.def, onChoose: _chooseModel, key: ValueKey('l$model')),
          if (hasCfg) _ConfigTab(widget.def, key: ValueKey('c$model')),
        ]),
      ),
    );
  }
}

/// Значение для показа: подпись из таблицы значений, текст или число с нужными знаками.
String formatValue(Param p, ParamValue v, AppLocalizations t, String lang) {
  if (v.label != null) return txt(v.label, lang);
  if (v.text != null) return v.text!;
  final n = v.number;
  if (n == null || n.isNaN) return '—';
  final s = n.toStringAsFixed(p.decimals);
  return lang == 'en' ? s : s.replaceAll('.', ',');
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
    case 'ms':
      return lang == 'en' ? 'ms' : 'мс';
    case 'mA':
      return lang == 'en' ? 'mA' : 'мА';
    case 'A':
      return lang == 'en' ? 'A' : 'А';
    case 'km':
      return lang == 'en' ? 'km' : 'км';
    case 'L':
      return lang == 'en' ? 'L' : 'л';
    case 's':
      return lang == 'en' ? 's' : 'с';
    default:
      return unit;
  }
}

/// Строки «название — значение» в карточке.
class _KvCard extends StatelessWidget {
  const _KvCard(this.rows);
  final List<(String, String)> rows;

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    return GlowCard(
      tint: p.border,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(children: [
        for (final (k, v) in rows)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 11),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(flex: 5, child: Text(k, style: TextStyle(color: p.textDim))),
              const SizedBox(width: 12),
              Expanded(
                flex: 4,
                child: Text(v, textAlign: TextAlign.right, style: mono(context, 14)),
              ),
            ]),
          ),
      ]),
    );
  }
}

class _IdentTab extends StatefulWidget {
  const _IdentTab(this.def, {required this.onChoose, super.key});
  final EcuDef def;
  final VoidCallback onChoose;
  @override
  State<_IdentTab> createState() => _IdentTabState();
}

class _IdentTabState extends State<_IdentTab> {
  EcuInfo? _info;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    AppScope.read(context).diag?.identify(widget.def).then(
          (v) => mounted ? setState(() => _info = v) : null,
          onError: (_) => mounted ? setState(() => _failed = true) : null,
        );
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final lang = AppScope.of(context).lang;
    final p = context.p;
    final diag = AppScope.of(context).diag;
    final l = diag?.link(widget.def);
    if (_info == null && !_failed) return const Center(child: CircularProgressIndicator());
    final canChoose = (diag?.modelChoices(widget.def).length ?? 0) > 1;
    final head = <(String, String)>[
      (t.model, l?.model == null ? t.modelUnknown : l!.model!.name),
      if (l?.part != null) (t.partNumber, l!.part!),
      if (l?.variant != null) (t.softwareVariant, l!.variant!),
      if (l?.proto != null) (t.protocol, l!.proto!.name),
      (t.address, '${widget.def.tx.toRadixString(16).toUpperCase()} → ${widget.def.rx.toRadixString(16).toUpperCase()}'),
      if (_info?.vin != null) (t.vin, _info!.vin!),
    ];
    final rows = [
      for (final (prm, v) in _info?.rows ?? const <(Param, ParamValue)>[])
        if (prm.key != 'VIN') (prm.nameFor(lang), '${formatValue(prm, v, t, lang)} ${liveUnit(prm.units, t, lang)}'.trim()),
    ];
    return ListView(padding: const EdgeInsets.all(20), children: [
      _KvCard(head),
      if (l?.model == null || l!.modelChosen) ...[
        const SizedBox(height: 12),
        if (l?.model == null) Text(t.chooseModelHint, style: TextStyle(color: p.textDim)),
        if (canChoose)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(onPressed: widget.onChoose, icon: const Icon(Icons.tune), label: Text(t.chooseModel)),
          ),
      ],
      if (rows.isNotEmpty) ...[const SizedBox(height: 14), _KvCard(rows)],
    ]);
  }
}

class _FaultsTab extends StatefulWidget {
  const _FaultsTab(this.def, {super.key});
  final EcuDef def;
  @override
  State<_FaultsTab> createState() => _FaultsTabState();
}

class _FaultsTabState extends State<_FaultsTab> {
  List<Dtc>? _dtcs;
  bool _busy = false;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await AppScope.read(context).diag?.readFaults(widget.def);
      if (mounted) setState(() => _dtcs = d ?? []);
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    }
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
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t.error('$e'))));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Какая ошибка раскрыта и её стоп-кадр (null — ещё грузится).
  String? _open;
  List<(Param, ParamValue)>? _snap;
  bool _snapFailed = false;

  Future<void> _toggle(Dtc d) async {
    if (_open == d.key) {
      setState(() => _open = null);
      return;
    }
    setState(() {
      _open = d.key;
      _snap = null;
      _snapFailed = false;
    });
    final diag = AppScope.read(context).diag;
    try {
      final s = await diag!.readSnapshot(widget.def, d);
      if (mounted && _open == d.key) setState(() => _snap = s);
    } catch (_) {
      if (mounted && _open == d.key) setState(() => _snapFailed = true);
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
            for (final (prm, v) in _snap!)
              Container(
                width: (box.maxWidth - 8) / 2,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(color: p.bg, borderRadius: BorderRadius.circular(12)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${prm.nameFor(lang)} · ${liveUnit(prm.units, t, lang)}',
                      maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, color: p.textDim)),
                  Text(formatValue(prm, v, t, lang), style: display(context, 18, w: FontWeight.w700)),
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
    if (_failed) return Center(child: Text(t.readFailed, style: TextStyle(color: p.textDim)));
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
            final info = app.diag?.dtcInfo(widget.def, d, app.lang);
            final open = _open == d.key;
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
                Text(info?.text ?? t.unknownFault, style: TextStyle(color: p.text)),
                if (info?.generic ?? false)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(t.genericSae, style: TextStyle(color: p.textDim, fontSize: 12)),
                  ),
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

/// Живые данные: группы (записи блока) кнопками сверху, опрашивается выбранная.
class _LiveTab extends StatefulWidget {
  const _LiveTab(this.def, {required this.onChoose, super.key});
  final EcuDef def;
  final VoidCallback onChoose;
  @override
  State<_LiveTab> createState() => _LiveTabState();
}

class _LiveTabState extends State<_LiveTab> {
  int _sel = 0;
  List<(Param, ParamValue)>? _vals;
  bool _failed = false;
  bool _run = true;
  int _gen = 0; // смена группы обрывает старый опрос

  List<Record> get _recs => AppScope.read(context).diag?.records(widget.def, 'live') ?? const [];

  @override
  void initState() {
    super.initState();
    _poll();
  }

  Future<void> _poll() async {
    final diag = AppScope.read(context).diag;
    final gen = ++_gen;
    while (_run && mounted && diag != null && gen == _gen && _sel < _recs.length) {
      try {
        final v = await diag.readRecord(widget.def, _recs[_sel]);
        if (!mounted || gen != _gen) return;
        setState(() {
          _vals = v;
          _failed = false;
        });
      } catch (_) {
        if (!mounted || gen != _gen) return;
        setState(() => _failed = true);
        await Future.delayed(const Duration(seconds: 1));
      }
      await Future.delayed(const Duration(milliseconds: 300));
    }
  }

  void _select(int i) {
    setState(() {
      _sel = i;
      _vals = null;
      _failed = false;
    });
    _poll();
  }

  @override
  void dispose() {
    _run = false;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final lang = AppScope.of(context).lang;
    final t = AppLocalizations.of(context);
    final p = context.p;
    final diag = AppScope.of(context).diag;
    final recs = _recs;
    if (diag?.link(widget.def).model == null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text(t.chooseModelHint, textAlign: TextAlign.center, style: TextStyle(color: p.textDim)),
            const SizedBox(height: 12),
            FilledButton.icon(onPressed: widget.onChoose, icon: const Icon(Icons.tune), label: Text(t.chooseModel)),
          ]),
        ),
      );
    }
    if (recs.isEmpty) return Center(child: Text(t.noData, style: TextStyle(color: p.textDim)));
    final vals = _vals;
    return Column(children: [
      SizedBox(
        height: 52,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.fromLTRB(20, 10, 20, 4),
          itemCount: recs.length,
          separatorBuilder: (_, _) => const SizedBox(width: 8),
          itemBuilder: (_, i) => ChoiceChip(
            label: Text('${recs[i].label} · ${recs[i].params.length}', style: mono(context, 13)),
            selected: i == _sel,
            onSelected: (_) => _select(i),
          ),
        ),
      ),
      Expanded(
        child: vals == null
            ? Center(child: _failed ? Text(t.readFailed, style: TextStyle(color: p.textDim)) : const CircularProgressIndicator())
            : GridView.count(
                padding: const EdgeInsets.all(20),
                crossAxisCount: 2,
                mainAxisSpacing: 12,
                crossAxisSpacing: 12,
                childAspectRatio: 1.6,
                children: [
                  for (final (prm, v) in vals)
                    GlowCard(
                      tint: p.info,
                      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        // сверху — что меряем, снизу — значение и единица (длинное название не съест единицу)
                        Text(
                          prm.nameFor(lang),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(fontSize: 13, height: 1.25, color: p.textDim),
                        ),
                        const Spacer(),
                        FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: Alignment.centerLeft,
                          child: Text.rich(TextSpan(children: [
                            TextSpan(text: formatValue(prm, v, t, lang), style: display(context, 26, w: FontWeight.w700)),
                            if (prm.units.isNotEmpty && v.label == null && v.text == null)
                              TextSpan(text: ' ${liveUnit(prm.units, t, lang)}', style: TextStyle(fontSize: 14, color: p.textDim)),
                          ])),
                        ),
                      ]),
                    ),
                ],
              ),
      ),
    ]);
  }
}

/// Настройки блока — только просмотр. Запись в приложении не делаем.
class _ConfigTab extends StatefulWidget {
  const _ConfigTab(this.def, {super.key});
  final EcuDef def;
  @override
  State<_ConfigTab> createState() => _ConfigTabState();
}

class _ConfigTabState extends State<_ConfigTab> {
  final _vals = <Record, List<(Param, ParamValue)>?>{};
  bool _done = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final diag = AppScope.read(context).diag;
    if (diag == null) return;
    for (final r in diag.records(widget.def, 'config')) {
      List<(Param, ParamValue)>? v;
      try {
        v = await diag.readRecord(widget.def, r);
      } catch (_) {
        v = null;
      }
      if (!mounted) return;
      setState(() => _vals[r] = v);
    }
    if (mounted) setState(() => _done = true);
  }

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final t = AppLocalizations.of(context);
    final lang = AppScope.of(context).lang;
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        for (final MapEntry(key: r, value: v) in _vals.entries) ...[
          Padding(
            padding: const EdgeInsets.only(bottom: 8, left: 4),
            child: Text(r.label, style: mono(context, 12, color: p.textDim)),
          ),
          if (v == null)
            Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 14),
              child: Text(t.readFailed, style: TextStyle(color: p.textDim)),
            )
          else ...[
            _KvCard([for (final (prm, x) in v) (prm.nameFor(lang), '${formatValue(prm, x, t, lang)} ${liveUnit(prm.units, t, lang)}'.trim())]),
            const SizedBox(height: 14),
          ],
        ],
        if (!_done) const Padding(padding: EdgeInsets.all(12), child: Center(child: CircularProgressIndicator())),
      ],
    );
  }
}
