import 'dart:io';

import 'package:flutter/material.dart';

import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../state/garage.dart';
import '../state/photo_store.dart';
import '../theme.dart';
import 'widgets.dart';

/// Гараж: все машины, которые сканировали. Новая добавляется сама по VIN после автоскана.
class GarageScreen extends StatefulWidget {
  const GarageScreen({super.key});
  @override
  State<GarageScreen> createState() => _GarageScreenState();
}

class _GarageScreenState extends State<GarageScreen> {
  final _store = PhotoStore();
  final _photos = <String, List<File>>{};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final cars = List.of(AppScope.read(context).garage.cars);
    for (final c in cars) {
      _photos[c.id] = await _store.list(c.id);
    }
    if (mounted) setState(() {});
  }

  Future<void> _edit(CarProfile c) async {
    final t = AppLocalizations.of(context);
    final app = AppScope.read(context);
    final name = TextEditingController(text: c.name);
    final sub = TextEditingController(text: c.sub);
    final res = await showDialog<String>(
      context: context,
      builder: (d) => AlertDialog(
        title: Text(t.edit),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: name, decoration: InputDecoration(labelText: t.carName)),
          const SizedBox(height: 8),
          TextField(controller: sub, decoration: InputDecoration(labelText: t.carSub)),
        ]),
        actions: [
          if (app.garage.cars.length > 1)
            TextButton(onPressed: () => Navigator.pop(d, 'delete'), child: Text(t.deleteCar, style: TextStyle(color: d.p.bad))),
          TextButton(onPressed: () => Navigator.pop(d), child: Text(t.cancel)),
          FilledButton(onPressed: () => Navigator.pop(d, 'save'), child: Text(t.save)),
        ],
      ),
    );
    if (!mounted) return;
    if (res == 'save') {
      app.updateCar(c.id, name: name.text.trim().isEmpty ? c.name : name.text.trim(), sub: sub.text.trim());
    } else if (res == 'delete') {
      final ok = await showDialog<bool>(
        context: context,
        builder: (d) => AlertDialog(
          content: Text(t.deleteCarConfirm),
          actions: [
            TextButton(onPressed: () => Navigator.pop(d, false), child: Text(t.cancel)),
            FilledButton(onPressed: () => Navigator.pop(d, true), child: Text(t.deleteCar)),
          ],
        ),
      );
      if (ok == true) {
        for (final f in _photos[c.id] ?? const <File>[]) {
          await _store.remove(f);
        }
        app.removeCar(c.id);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final t = AppLocalizations.of(context);
    final p = context.p;
    return Scaffold(
      appBar: AppBar(backgroundColor: p.bg, title: Text(t.garage)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
        children: [
          Text(t.garageSub, style: TextStyle(color: p.textDim)),
          const SizedBox(height: 14),
          for (final c in app.garage.cars) ...[
            _card(context, c, c.id == app.garage.currentId),
            const SizedBox(height: 12),
          ],
          Row(children: [
            Icon(Icons.info_outline, size: 18, color: p.textDim),
            const SizedBox(width: 8),
            Expanded(child: Text(t.garageHint, style: TextStyle(fontSize: 13, color: p.textDim))),
          ]),
        ],
      ),
    );
  }

  Widget _card(BuildContext context, CarProfile c, bool current) {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final photos = _photos[c.id] ?? const <File>[];
    final scanned = c.lastScan;
    return GlowCard(
      tint: current ? p.info : p.border,
      padding: const EdgeInsets.all(12),
      onTap: () {
        AppScope.read(context).selectCar(c.id);
        Navigator.pop(context);
      },
      child: Row(children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(14),
          child: SizedBox(
            width: 104,
            height: 74,
            child: photos.isNotEmpty
                ? Image.file(photos.first, fit: BoxFit.cover, cacheWidth: 300)
                : Image.asset('assets/img/car_c3.jpg', fit: BoxFit.cover),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text(c.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: display(context, 17, w: FontWeight.w700))),
              if (current) Pill(t.currentCar, fg: Colors.white, bg: p.good),
            ]),
            if (c.sub.isNotEmpty) Text(c.sub, style: TextStyle(fontSize: 13, color: p.textDim)),
            if (c.vin != null) Text(c.vin!, style: mono(context, 12, color: p.textDim)),
            const SizedBox(height: 6),
            Wrap(spacing: 6, runSpacing: 4, children: [
              if (c.lastFaults != null)
                Pill(t.faultCount(c.lastFaults!),
                    fg: c.lastFaults! > 0 ? p.bad : p.good,
                    bg: (c.lastFaults! > 0 ? p.bad : p.good).withValues(alpha: 0.12)),
              Pill(scanned == null ? t.neverScanned : t.lastScanAt('${scanned.day.toString().padLeft(2, '0')}.${scanned.month.toString().padLeft(2, '0')}'),
                  fg: p.textDim, bg: p.textDim.withValues(alpha: 0.12)),
              Pill(t.photosCount(photos.length), fg: p.textDim, bg: p.textDim.withValues(alpha: 0.12)),
            ]),
          ]),
        ),
        IconButton(
          tooltip: t.edit,
          icon: Icon(Icons.edit_outlined, color: p.textDim),
          onPressed: () => _edit(c),
        ),
      ]),
    );
  }
}
