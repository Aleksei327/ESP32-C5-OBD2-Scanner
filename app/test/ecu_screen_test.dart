import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:scaner_app/l10n/gen/app_localizations.dart';
import 'package:scaner_app/main.dart';
import 'package:scaner_app/state/app_state.dart';
import 'package:scaner_app/state/diag_service.dart';
import 'package:scaner_app/state/scan_store.dart';
import 'package:scaner_app/theme.dart';
import 'package:scaner_app/ui/ecu_detail_screen.dart';
import 'package:scaner_app/ui/scan_screen.dart';

import 'diag_test.dart' show FakeClient, loadKb;

/// Двигатель V46 на подставном адаптере: сеанс, опознание, две ошибки, живые данные C0.
FakeClient engineOnly() {
  final c0 = List.filled(56, 0);
  c0[0] = 0x03; // обороты 800
  c0[1] = 0x20;
  c0[2] = 141; // 14,1 В
  c0[3] = 140; // 90 °C
  return FakeClient((tx, req) {
    if (tx != 0x6A8) return null;
    switch (req.map((b) => b.toRadixString(16).padLeft(2, '0')).join().toUpperCase()) {
      case '81':
        return [0xC1, 0xD0, 0x8F];
      case '21FE':
        return [0x61, 0xFE, ...List.filled(21, 0), 0x78, 0x91, 0x68];
      case '2180':
        return [0x61, 0x80, ...List.filled(17, 0x31)];
      case '17FF00':
        return [0x57, 0x02, 0x01, 0x30, 0x60, 0x03, 0x00, 0x20];
      case '21C0':
        return [0x61, 0xC0, ...c0];
    }
    return [0x7F, req.first, 0x31];
  });
}

Widget host(AppState app, Widget home) => AppScope(
      state: app,
      child: MaterialApp(
        locale: const Locale('ru'),
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        theme: buildTheme(AppThemeKind.bright),
        home: home,
      ),
    );

/// Экраны на подставном адаптере: строятся без ошибок и переполнений, сохранённое показывают сами.
void main() {
  setUp(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('«Блоки» показывают сохранённый скан и сами машину не опрашивают', (tester) async {
    final kb = loadKb();
    final fake = engineOnly();
    final app = (await tester.runAsync(AppState.create))!; // читает сканы с диска — на настоящих часах
    app.kb = kb;
    app.diag = DiagService(fake, kb);
    final eng = kb.ecus.firstWhere((e) => e.node == 'CMM');
    app.scans = [
      SavedScan(id: '1', time: DateTime(2026, 11, 2, 11, 18), ecus: [
        for (final d in kb.ecus) SavedEcu(tx: d.tx, answered: d == eng, time: DateTime(2026, 11, 2, 11, 18), model: d == eng ? 'V46' : null),
      ]),
    ];
    await tester.binding.setSurfaceSize(const Size(400, 860));
    await tester.pumpWidget(host(app, const ScanScreen()));
    await tester.pump(const Duration(milliseconds: 300));
    expect(fake.sent, isEmpty);
    expect(find.text('Скан 02.11.2026 11:18'), findsOneWidget);
    expect(find.textContaining('V46'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('экран блока двигателя: инфо, ошибки, данные', (tester) async {
    final kb = loadKb();
    final fake = engineOnly();
    final app = (await tester.runAsync(AppState.create))!; // читает сканы с диска — на настоящих часах
    final diag = DiagService(fake, kb);
    app.kb = kb;
    app.diag = diag;
    final eng = kb.ecus.firstWhere((e) => e.node == 'CMM');
    final l = diag.link(eng);
    await tester.runAsync(() async {
      final links = await diag.autoScan().toList();
      app.scans = [SavedScan(id: '1', time: DateTime.now(), ecus: [for (final x in links) x.saved()])];
    });
    expect(l.model?.name, 'V46');

    await tester.binding.setSurfaceSize(const Size(400, 860));
    await tester.pumpWidget(host(app, EcuDetailScreen(eng)));
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('V46'), findsWidgets);

    Future<void> frames() async {
      for (var i = 0; i < 8; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
    }

    await tester.tap(find.text('Ошибки'));
    await frames();
    expect(find.text('P0130'), findsOneWidget);
    expect(find.text('активна'), findsOneWidget);

    await tester.tap(find.text('Данные'));
    await frames();
    expect(find.textContaining('C0 ·'), findsOneWidget);
    expect(find.textContaining('800'), findsWidgets);
    expect(find.textContaining('90 °C'), findsWidgets);

    // закрыть экран и дать доиграть таймерам опроса
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 2));
  });
}
