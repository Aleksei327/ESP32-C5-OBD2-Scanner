import 'package:flutter/material.dart';

import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../theme.dart';
import 'widgets.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final t = AppLocalizations.of(context);
    final p = context.p;
    return Scaffold(
      appBar: AppBar(title: Text(t.settings), backgroundColor: p.bg),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          _label(context, t.language),
          _segment(context, [
            ('Русский', app.lang == 'ru', () => app.setLocale('ru')),
            ('English', app.lang == 'en', () => app.setLocale('en')),
          ]),
          const SizedBox(height: 20),
          _label(context, t.theme),
          Row(children: [
            Expanded(child: _themeCard(context, AppThemeKind.engineering, t.themeEngineering, t.themeEngineeringSub)),
            const SizedBox(width: 12),
            Expanded(child: _themeCard(context, AppThemeKind.bright, t.themeBright, t.themeBrightSub)),
          ]),
          const SizedBox(height: 20),
          _label(context, t.general),
          GlowCard(
            tint: p.textDim,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(children: [
              _row(context, t.firmware, app.fw.isEmpty ? '—' : app.fw),
              Divider(color: p.border, height: 1),
              _row(context, t.battery, t.volts(app.batteryText)),
              Divider(color: p.border, height: 1),
              _row(context, t.adapterAddress, app.adapterUrl),
            ]),
          ),
          const SizedBox(height: 16),
          Row(children: [
            Icon(Icons.public, size: 20, color: p.info),
            const SizedBox(width: 10),
            Expanded(child: Text(t.translationNote, style: TextStyle(fontSize: 13, color: p.textDim))),
          ]),
          const SizedBox(height: 24),
          OutlinedButton.icon(
            onPressed: () {
              app.disconnect();
              Navigator.of(context).popUntil((r) => r.isFirst);
            },
            icon: const Icon(Icons.link_off),
            label: Text(t.disconnect),
          ),
        ],
      ),
    );
  }

  Widget _label(BuildContext c, String s) => Padding(
        padding: const EdgeInsets.only(bottom: 10, left: 4),
        child: Text(s.toUpperCase(),
            style: TextStyle(fontSize: 12, letterSpacing: 0.6, fontWeight: FontWeight.w600, color: c.p.textDim)),
      );

  Widget _segment(BuildContext c, List<(String, bool, VoidCallback)> items) {
    final p = c.p;
    return Container(
      padding: const EdgeInsets.all(5),
      decoration: BoxDecoration(color: p.surface, borderRadius: BorderRadius.circular(16), border: Border.all(color: p.border)),
      child: Row(
        children: [
          for (final (label, on, tap) in items)
            Expanded(
              child: GestureDetector(
                onTap: tap,
                child: Container(
                  height: 46,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    gradient: on ? LinearGradient(colors: [p.accent, p.info]) : null,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(label,
                      style: TextStyle(fontWeight: FontWeight.w600, color: on ? p.onAccent : p.textDim)),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _themeCard(BuildContext c, AppThemeKind kind, String name, String sub) {
    final app = AppScope.of(c);
    final p = c.p;
    final on = app.theme == kind;
    final prev = AppPalette.of(kind);
    return GestureDetector(
      onTap: () => app.setTheme(kind),
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: p.surface,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: on ? p.info : p.border, width: on ? 2 : 1),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            height: 70,
            decoration: BoxDecoration(color: prev.bg, borderRadius: BorderRadius.circular(12)),
            padding: const EdgeInsets.all(10),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Container(height: 8, width: 50, color: prev.text),
              const SizedBox(height: 6),
              Container(height: 16, decoration: BoxDecoration(color: prev.surface, borderRadius: BorderRadius.circular(4))),
              const Spacer(),
              Container(height: 12, width: 60, decoration: BoxDecoration(color: prev.accent, borderRadius: BorderRadius.circular(4))),
            ]),
          ),
          const SizedBox(height: 8),
          Text(name, style: TextStyle(fontWeight: FontWeight.w600, color: p.text)),
          Text(sub, style: TextStyle(fontSize: 12, color: p.textDim)),
        ]),
      ),
    );
  }

  Widget _row(BuildContext c, String k, String v) => SizedBox(
        height: 52,
        child: Row(children: [
          Text(k, style: TextStyle(color: c.p.text)),
          const Spacer(),
          Flexible(child: Text(v, overflow: TextOverflow.ellipsis, style: TextStyle(color: c.p.textDim))),
        ]),
      );
}
