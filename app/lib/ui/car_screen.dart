import 'dart:io';

import 'package:flutter/material.dart';

import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../state/photo_store.dart';
import '../theme.dart';
import 'garage_screen.dart';
import 'settings_screen.dart';
import 'widgets.dart';

/// Главный экран: машина, плашки (АКБ, ошибки, блоки), автоскан, фото, плитки разделов.
class CarScreen extends StatefulWidget {
  const CarScreen({super.key});
  @override
  State<CarScreen> createState() => _CarScreenState();
}

class _CarScreenState extends State<CarScreen> {
  final _store = PhotoStore();
  List<File> _photos = [];

  String get _carKey => AppScope.read(context).car.id;
  String? _loadedFor; // для какой машины загружены фото


  Future<void> _loadPhotos() async {
    final list = await _store.list(_carKey);
    if (mounted) setState(() => _photos = list);
  }

  Future<void> _addPhoto() async {
    final t = AppLocalizations.of(context);
    final p = context.p;
    final camera = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: p.surface,
      showDragHandle: true,
      builder: (c) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: Icon(Icons.photo_camera_outlined, color: p.accent),
              title: Text(t.camera),
              onTap: () => Navigator.pop(c, true),
            ),
            ListTile(
              leading: Icon(Icons.photo_library_outlined, color: p.accent),
              title: Text(t.gallery),
              onTap: () => Navigator.pop(c, false),
            ),
          ],
        ),
      ),
    );
    if (camera == null) return;
    await _store.add(_carKey, camera: camera);
    await _loadPhotos();
  }

  Future<void> _openPhoto(File f) async {
    final t = AppLocalizations.of(context);
    final deleted = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (c) => Scaffold(
          backgroundColor: Colors.black,
          appBar: AppBar(
            backgroundColor: Colors.black,
            foregroundColor: Colors.white,
            actions: [
              IconButton(
                tooltip: t.deletePhoto,
                icon: const Icon(Icons.delete_outline),
                onPressed: () => Navigator.pop(c, true),
              ),
            ],
          ),
          body: Center(child: InteractiveViewer(child: Image.file(f))),
        ),
      ),
    );
    if (deleted == true) {
      await _store.remove(f);
      await _loadPhotos();
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final t = AppLocalizations.of(context);
    final p = context.p;
    final faults = app.lastFaults;
    if (_loadedFor != app.car.id) {
      _loadedFor = app.car.id;
      _photos = [];
      _loadPhotos();
    }
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
          children: [
            Row(
              children: [
                Expanded(
                  // нажатие на название — в гараж, выбрать другую машину
                  child: InkWell(
                    borderRadius: BorderRadius.circular(12),
                    onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const GarageScreen())),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Flexible(
                              child: Text(
                                app.car.name,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: display(context, 28),
                              ),
                            ),
                            Icon(Icons.expand_more, color: p.textDim),
                          ],
                        ),
                        Text(app.car.sub.isEmpty ? t.garage : app.car.sub, style: TextStyle(color: p.textDim)),
                      ],
                    ),
                  ),
                ),
                _statusChip(context, app.connected, t),
                IconButton(
                  icon: Icon(Icons.settings_outlined, color: p.textDim),
                  onPressed: () =>
                      Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SettingsScreen())),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Container(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(22),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF2F7BF6).withValues(alpha: p.isBright ? 0.35 : 0.25),
                    blurRadius: 30,
                    offset: const Offset(0, 12),
                  ),
                ],
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(22),
                child: AspectRatio(
                  aspectRatio: 3 / 2,
                  child: Image.asset('assets/img/car_c3.jpg', fit: BoxFit.cover),
                ),
              ),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(child: _stat(context, t.battery, t.volts(app.batteryText), p.good, () => app.tab.value = 2)),
                const SizedBox(width: 10),
                Expanded(child: _stat(context, t.faults, faults == null ? '—' : '$faults', p.bad, () => app.tab.value = 1)),
                const SizedBox(width: 10),
                Expanded(child: _stat(context, t.modules, '${app.lastAnswered ?? '—'}', p.info, () => app.tab.value = 1)),
              ],
            ),
            const SizedBox(height: 14),
            _scanButton(context, t),
            const SizedBox(height: 18),
            Row(
              children: [
                Expanded(
                  child: Text(t.photos, style: display(context, 16, w: FontWeight.w700)),
                ),
                Text(t.photosCount(_photos.length), style: TextStyle(fontSize: 13, color: p.textDim)),
              ],
            ),
            const SizedBox(height: 10),
            _photoRow(context, t),
          ],
        ),
      ),
    );
  }

  Widget _scanButton(BuildContext context, AppLocalizations t) {
    final p = context.p;
    final app = AppScope.read(context);
    final fg = p.onAccent;
    final radius = BorderRadius.circular(18);
    return Container(
      height: 64,
      decoration: BoxDecoration(
        borderRadius: radius,
        color: p.isBright ? null : p.accent,
        gradient: p.isBright ? const LinearGradient(colors: [Color(0xFF0E7490), Color(0xFF6D28D9)]) : null,
        boxShadow: p.cardShadow(const Color(0xFF6D28D9)),
      ),
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          borderRadius: radius,
          onTap: app.requestScan,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 18),
            child: Row(
              children: [
                Icon(Icons.radar, color: fg, size: 28),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(t.autoScan, style: display(context, 19).copyWith(color: fg)),
                      Text(t.autoScanSub, style: TextStyle(fontSize: 13, color: fg.withValues(alpha: 0.85))),
                    ],
                  ),
                ),
                Icon(Icons.chevron_right, color: fg),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _photoRow(BuildContext context, AppLocalizations t) {
    final p = context.p;
    final canAdd = _photos.length < PhotoStore.maxPhotos;
    final cells = <Widget>[
      for (final f in _photos)
        GestureDetector(
          onTap: () => _openPhoto(f),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: Image.file(f, fit: BoxFit.cover, cacheWidth: 240),
          ),
        ),
      if (canAdd)
        GestureDetector(
          onTap: _addPhoto,
          child: Container(
            decoration: BoxDecoration(
              color: p.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: p.info, width: 1.5),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.add_a_photo_outlined, color: p.info, size: 22),
                const SizedBox(height: 3),
                Text(t.addPhoto, style: TextStyle(fontSize: 11, color: p.info)),
              ],
            ),
          ),
        ),
    ];
    return GridView.count(
      crossAxisCount: 5,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 8,
      children: cells,
    );
  }

  Widget _statusChip(BuildContext c, bool on, AppLocalizations t) {
    final p = c.p;
    final col = on ? p.good : p.textDim;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: p.surface,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: col.withValues(alpha: 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: col, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(
            on ? t.connected : t.notConnected,
            style: TextStyle(fontSize: 13, color: col, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }

  Widget _stat(BuildContext c, String label, String value, Color tint, VoidCallback onTap) => GlowCard(
    tint: tint,
    onTap: onTap,
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(label, style: TextStyle(fontSize: 12, color: tint, fontWeight: FontWeight.w600)),
            ),
            Icon(Icons.chevron_right, size: 16, color: tint),
          ],
        ),
        Text(value, style: display(c, 22, w: FontWeight.w700)),
      ],
    ),
  );

}
