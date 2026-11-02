import 'package:flutter/material.dart';

import '../kb/knowledge_base.dart';
import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../state/app_state.dart';
import '../state/diag_service.dart';
import '../state/scan_store.dart';
import '../theme.dart';
import '../transport/diag.dart';
import 'widgets.dart';

/// Этот блок в открытом скане: что сохранено (модель, ошибки) и когда опрошен.
SavedEcu? savedEcu(AppState app, EcuDef d) => app.shownScan?.ecu(d.tx);

/// Модель блока: опознанная в этом подключении, иначе из скана.
EcuModel? ecuModel(AppState app, EcuDef d) => app.diag?.link(d).model ?? d.modelNamed(savedEcu(app, d)?.model);

/// Блок: вкладки Инфо / Ошибки / Данные / Опции. Инфо и ошибки — из сохранённого скана,
/// данные и опции читаются вживую, когда адаптер подключён. Опрос — через DiagService.
class EcuDetailScreen extends StatefulWidget {
  const EcuDetailScreen(this.def, {super.key});
  final EcuDef def;
  @override
  State<EcuDetailScreen> createState() => _EcuDetailScreenState();
}

class _EcuDetailScreenState extends State<EcuDetailScreen> with TickerProviderStateMixin {
  TabController? _tabs;
  bool _rescanning = false;

  bool _hasConfig(AppState app) {
    final saved = savedEcu(app, widget.def);
    final variant = app.diag?.link(widget.def).variant ?? saved?.variant;
    return ecuModel(app, widget.def)?.recordsFor(variant, 'config').isNotEmpty ?? false;
  }

  /// Опросить заново только этот блок; итог — новый скан в истории (остальные блоки из прошлого).
  Future<void> _rescan() async {
    final app = AppScope.read(context);
    final t = AppLocalizations.of(context);
    final diag = app.diag;
    final last = app.scans.firstOrNull;
    if (diag == null || last == null) return;
    setState(() => _rescanning = true);
    try {
      final l = await diag.rescan(widget.def);
      await app.saveScan(last.withEcu(l.saved(), module: widget.def.node, batteryMv: app.batteryMv, fw: app.fw));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t.error('$e'))));
    } finally {
      if (mounted) setState(() => _rescanning = false);
    }
  }

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
    final hasCfg = _hasConfig(app);
    _syncTabs(hasCfg ? 4 : 3);
    final model = ecuModel(app, widget.def)?.name ?? '';
    final saved = savedEcu(app, widget.def);
    // пересканировать можно последний скан и только вживую; старый из истории — только смотреть
    final canRescan = app.live && !app.viewingOld && app.scans.isNotEmpty;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: p.bg,
        title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(widget.def.nameFor(lang), style: TextStyle(fontSize: 18, color: p.text)),
          Text(
              '${widget.def.tx.toRadixString(16).toUpperCase()} → ${widget.def.rx.toRadixString(16).toUpperCase()}'
              '${model.isEmpty ? '' : ' · $model'}',
              style: mono(context, 12, color: p.textDim)),
          if (saved != null) Text(t.moduleReadAt(stamp(saved.time)), style: TextStyle(fontSize: 12, color: p.textDim)),
        ]),
        actions: [
          if (canRescan)
            IconButton(
              tooltip: t.rescanModule,
              onPressed: _rescanning ? null : _rescan,
              icon: _rescanning
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : Icon(Icons.refresh, color: p.accent),
            ),
          const SizedBox(width: 8),
        ],
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
        // ключ со временем опроса: пересканировали — вкладки строятся заново по новому итогу
        child: TabBarView(controller: _tabs, children: [
          _IdentTab(widget.def, onChoose: _chooseModel, key: ValueKey('i$model${saved?.time}')),
          _FaultsTab(widget.def, onRescan: canRescan ? _rescan : null, key: ValueKey('f$model${saved?.time}')),
          app.live ? _LiveTab(widget.def, onChoose: _chooseModel, key: ValueKey('l$model')) : const NeedAdapter(),
          if (hasCfg) app.live ? _ConfigTab(widget.def, key: ValueKey('c$model')) : const NeedAdapter(),
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
    // сохранённое показываем сразу; записи опознания дочитываем, если адаптер подключён
    final app = AppScope.read(context);
    final diag = app.diag;
    if (diag == null) return;
    diag.attach(widget.def, savedEcu(app, widget.def)).then((_) => diag.identify(widget.def)).then(
          (v) => mounted ? setState(() => _info = v) : null,
          onError: (_) => mounted ? setState(() => _failed = true) : null,
        );
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final app = AppScope.of(context);
    final lang = app.lang;
    final p = context.p;
    final diag = app.diag;
    final l = diag?.link(widget.def);
    final saved = savedEcu(app, widget.def);
    final model = ecuModel(app, widget.def);
    final part = l?.part ?? saved?.part;
    final variant = l?.variant ?? saved?.variant;
    final proto = l?.proto?.name ?? switch (saved?.proto) { 'kwp' => 'KWP2000', 'uds' => 'UDS', _ => null };
    final canChoose = (diag?.modelChoices(widget.def).length ?? 0) > 1;
    final head = <(String, String)>[
      (t.model, model == null ? t.modelUnknown : model.name),
      if (part != null) (t.partNumber, part),
      if (variant != null) (t.softwareVariant, variant),
      if (proto != null) (t.protocol, proto),
      (t.address, '${widget.def.tx.toRadixString(16).toUpperCase()} → ${widget.def.rx.toRadixString(16).toUpperCase()}'),
      if (_info?.vin != null) (t.vin, _info!.vin!),
    ];
    final rows = [
      for (final (prm, v) in _info?.rows ?? const <(Param, ParamValue)>[])
        if (prm.key != 'VIN') (prm.nameFor(lang), '${formatValue(prm, v, t, lang)} ${liveUnit(prm.units, t, lang)}'.trim()),
    ];
    return ListView(padding: const EdgeInsets.all(20), children: [
      _KvCard(head),
      if (diag != null && (l?.model == null || l!.modelChosen)) ...[
        const SizedBox(height: 12),
        if (l?.model == null) Text(t.chooseModelHint, style: TextStyle(color: p.textDim)),
        if (canChoose)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(onPressed: widget.onChoose, icon: const Icon(Icons.tune), label: Text(t.chooseModel)),
          ),
      ],
      if (rows.isNotEmpty) ...[const SizedBox(height: 14), _KvCard(rows)],
      if (diag != null && _info == null && !_failed)
        const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator())),
    ]);
  }
}

/// Ошибки из открытого скана. Сброс — только вживую и в последнем скане: после него блок
/// пересканируется, и в истории остаются оба итога, до и после.
class _FaultsTab extends StatefulWidget {
  const _FaultsTab(this.def, {required this.onRescan, super.key});
  final EcuDef def;
  final Future<void> Function()? onRescan;
  @override
  State<_FaultsTab> createState() => _FaultsTabState();
}

class _FaultsTabState extends State<_FaultsTab> {
  bool _busy = false;

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
    final app = AppScope.read(context);
    final diag = app.diag;
    if (diag == null) return;
    setState(() => _busy = true);
    try {
      await diag.attach(widget.def, savedEcu(app, widget.def));
      await diag.clearFaults(widget.def);
      await widget.onRescan?.call();
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
    final app = AppScope.read(context);
    final diag = app.diag;
    try {
      await diag!.attach(widget.def, savedEcu(app, widget.def));
      final s = await diag.readSnapshot(widget.def, d);
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
    final dtcs = savedEcu(app, widget.def)?.dtcs ?? const <Dtc>[];
    final model = ecuModel(app, widget.def);
    // стоп-кадр читается из блока — только вживую
    final live = app.live;
    if (dtcs.isEmpty) {
      return Center(child: Text(t.noFaults, style: TextStyle(color: p.textDim)));
    }
    return Column(children: [
      Expanded(
        child: ListView.separated(
          padding: const EdgeInsets.all(20),
          itemCount: dtcs.length,
          separatorBuilder: (_, _) => const SizedBox(height: 10),
          itemBuilder: (_, i) {
            final d = dtcs[i];
            final info = app.kb == null ? null : dtcInfoFor(app.kb!, widget.def, model, d, app.lang);
            final open = live && _open == d.key;
            return GlowCard(
              tint: d.active ? p.bad : p.border,
              onTap: live ? () => _toggle(d) : null,
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Text(d.code, style: mono(context, 16).copyWith(fontWeight: FontWeight.w600)),
                  if (!widget.def.saeP && d.psa != null)
                    Text('  PSA ${d.psa}', style: mono(context, 13).copyWith(color: p.textDim)),
                  const Spacer(),
                  Pill(d.active ? t.faultActive : t.faultStored,
                      fg: d.active ? Colors.white : p.textDim,
                      bg: d.active ? p.bad : p.textDim.withValues(alpha: 0.12)),
                  if (live) Icon(open ? Icons.expand_less : Icons.expand_more, color: p.textDim),
                ]),
                const SizedBox(height: 6),
                Text(info?.text ?? t.unknownFault, style: TextStyle(color: p.text)),
                if (info?.check != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(t.faultCheck(info!.check!), style: TextStyle(color: p.textDim, fontSize: 13)),
                  ),
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
      if (widget.onRescan != null)
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
  bool _attached = false;

  List<Record> get _recs => AppScope.read(context).diag?.records(widget.def, 'live') ?? const [];

  @override
  void initState() {
    super.initState();
    _start();
  }

  /// Блок мог прийти из сохранённого скана: сначала сеанс и модель, потом опрос.
  Future<void> _start() async {
    final app = AppScope.read(context);
    try {
      await app.diag?.attach(widget.def, savedEcu(app, widget.def));
    } catch (_) {}
    if (!mounted) return;
    setState(() => _attached = true);
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
    if (!_attached) return const Center(child: CircularProgressIndicator());
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
    final app = AppScope.read(context);
    final diag = app.diag;
    if (diag == null) return;
    try {
      await diag.attach(widget.def, savedEcu(app, widget.def));
    } catch (_) {}
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
