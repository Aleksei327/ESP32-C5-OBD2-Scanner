import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_localizations/flutter_localizations.dart';

import 'l10n/gen/app_localizations.dart';
import 'state/app_state.dart';
import 'theme.dart';
import 'ui/bus_screen.dart';
import 'ui/car_screen.dart';
import 'ui/connect_screen.dart';
import 'ui/gauges_screen.dart';
import 'ui/scan_screen.dart';
import 'ui/widgets.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  _registerLicenses();
  runApp(ScanerApp(await AppState.create()));
}

/// Чужие данные и шрифты в приложении — с их лицензиями (Настройки → Лицензии).
void _registerLicenses() {
  LicenseRegistry.addLicense(() async* {
    yield LicenseEntryWithLineBreaks(
        ['PSA-RE (knowledge base data, github.com/prototux/PSA-RE)'], await rootBundle.loadString('assets/kb/PSA-RE-LICENCE.txt'));
    yield LicenseEntryWithLineBreaks(
        ['ludwig-v/arduino-psa-diag (extra PSA fault code texts, assets/kb/c3_ii_dtc_gpl.json)'],
        await rootBundle.loadString('assets/kb/GPL-3.0.txt'));
    yield const LicenseEntryWithLineBreaks(['OBD Codes List (generic SAE J2012 fault code texts)'],
        'Code data from OBD Codes List, https://obdcodeslist.com/code-data.html\n'
        'via github.com/tekseport/obd2-codes. Free to use, including commercial use, with this attribution.');
    for (final (name, file) in const [
      ('Exo 2', 'OFL-exo2.txt'),
      ('IBM Plex Sans', 'OFL-ibmplexsans.txt'),
      ('IBM Plex Mono', 'OFL-ibmplexmono.txt'),
    ]) {
      yield LicenseEntryWithLineBreaks([name], await rootBundle.loadString('assets/google_fonts/$file'));
    }
  });
}

/// Делает AppState доступным через AppScope.of(context) и пересобирает дерево.
class AppScope extends InheritedNotifier<AppState> {
  const AppScope({super.key, required AppState state, required super.child})
      : super(notifier: state);
  /// В build(): подписывается на изменения состояния.
  static AppState of(BuildContext c) =>
      c.dependOnInheritedWidgetOfExactType<AppScope>()!.notifier!;

  /// В initState() и колбэках: просто взять, без подписки.
  static AppState read(BuildContext c) =>
      c.getInheritedWidgetOfExactType<AppScope>()!.notifier!;
}

class ScanerApp extends StatelessWidget {
  const ScanerApp(this.state, {super.key});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    return AppScope(
      state: state,
      child: AnimatedBuilder(
        animation: state,
        builder: (context, _) => MaterialApp(
          title: 'OBD Scanner',
          debugShowCheckedModeBanner: false,
          locale: state.locale,
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          theme: buildTheme(state.theme),
          home: state.connected ? const HomeShell() : const ConnectScreen(),
        ),
      ),
    );
  }
}

/// Нижнее меню: Машина / Блоки / Датчики / Шина. Настройки — из экрана машины.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  late final AppState _app;
  int get _tab => _app.tab.value;

  @override
  void initState() {
    super.initState();
    _app = AppScope.read(context);
    _app.tab.addListener(_onTab);
  }

  void _onTab() => setState(() {});

  @override
  void dispose() {
    _app.tab.removeListener(_onTab);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final pages = const [CarScreen(), ScanScreen(), GaugesScreen(), BusScreen()];
    return Scaffold(
      // Строим только открытую вкладку: каждая сама открывает нужную ей шину,
      // и они не должны работать одновременно (скан и монитор делят шину B).
      body: pages[_tab],
      bottomNavigationBar: GlowNavBar(
        index: _tab,
        onTap: (i) => _app.tab.value = i,
        items: [
          NavItem(Icons.directions_car_rounded, t.navCar, const Color(0xFF2F7BF6)),
          NavItem(Icons.dashboard_rounded, t.navModules, const Color(0xFF8B5CF6)),
          NavItem(Icons.speed_rounded, t.navGauges, const Color(0xFFF59E0B)),
          NavItem(Icons.lan_rounded, t.navBus, const Color(0xFF06B6D4)),
        ],
      ),
    );
  }
}
