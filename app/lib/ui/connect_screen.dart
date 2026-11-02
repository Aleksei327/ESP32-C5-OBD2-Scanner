import 'package:flutter/material.dart';

import '../l10n/gen/app_localizations.dart';
import '../main.dart';
import '../theme.dart';
import 'widgets.dart';

class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key});
  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  late final TextEditingController _url;
  late final TextEditingController _ssid;
  late final TextEditingController _pass;

  @override
  void initState() {
    super.initState();
    final app = AppScope.read(context);
    _url = TextEditingController(text: app.adapterUrl);
    _ssid = TextEditingController(text: app.wifiSsid);
    _pass = TextEditingController(text: app.wifiPass);
  }

  @override
  void dispose() {
    _url.dispose();
    _ssid.dispose();
    _pass.dispose();
    super.dispose();
  }

  /// Человеческий текст вместо «TimeoutException after 0:00:06…».
  String _friendly(AppLocalizations t, String err) {
    if (err == 'wifi_join') return t.errWifi;
    if (err.contains('Timeout')) return t.errTimeout;
    if (err.contains('refused')) return t.errRefused;
    return t.connectFailed(err);
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final t = AppLocalizations.of(context);
    final p = context.p;
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            const SizedBox(height: 24),
            Row(children: [
              Container(
                width: 48, height: 48,
                decoration: BoxDecoration(color: p.accent.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(14)),
                child: Icon(Icons.wifi_tethering, color: p.accent),
              ),
              const SizedBox(width: 12),
              Expanded(child: Text(t.appTitle, style: display(context, 24))),
            ]),
            const SizedBox(height: 28),
            GlowCard(
              tint: p.info,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t.adapterAddress, style: TextStyle(fontWeight: FontWeight.w600, color: p.text)),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _url,
                    style: mono(context, 14),
                    decoration: InputDecoration(
                      hintText: 'ws://…',
                      helperText: t.adapterHint,
                      helperMaxLines: 2,
                      border: const OutlineInputBorder(),
                    ),
                    onChanged: app.setUrl,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            GlowCard(
              tint: p.info,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t.adapterWifi, style: TextStyle(fontWeight: FontWeight.w600, color: p.text)),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _ssid,
                    style: mono(context, 14),
                    autocorrect: false,
                    decoration: InputDecoration(labelText: t.adapterWifiSsid, border: const OutlineInputBorder()),
                    onChanged: (_) => app.setWifi(_ssid.text, _pass.text),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _pass,
                    style: mono(context, 14),
                    autocorrect: false,
                    enableSuggestions: false,
                    decoration: InputDecoration(
                      labelText: t.adapterWifiPass,
                      helperText: t.adapterWifiHint,
                      helperMaxLines: 5,
                      border: const OutlineInputBorder(),
                    ),
                    onChanged: (_) => app.setWifi(_ssid.text, _pass.text),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            if (app.connectError != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(_friendly(t, app.connectError!), style: TextStyle(color: p.bad)),
              ),
            const SizedBox(height: 8),
            FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: p.accent, foregroundColor: p.onAccent, minimumSize: const Size.fromHeight(56)),
              onPressed: app.connecting ? null : () => app.connect(),
              child: app.connecting
                  ? Text(t.connecting)
                  : Text(t.connect, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
            ),
            const SizedBox(height: 12),
            // без адаптера: гараж и сохранённые сканы
            TextButton.icon(
              onPressed: app.connecting ? null : app.openOffline,
              icon: const Icon(Icons.history),
              label: Text(t.openOffline),
            ),
          ],
        ),
      ),
    );
  }
}
