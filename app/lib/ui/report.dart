import 'dart:io';

import 'package:flutter/services.dart' show rootBundle;
import 'package:path_provider/path_provider.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:share_plus/share_plus.dart';

import '../l10n/gen/app_localizations.dart';
import '../state/app_state.dart';
import '../state/diag_service.dart';
import 'ecu_detail_screen.dart' show liveUnit;

/// Отчёт по автоскану в PDF: машина, блоки, ошибки с расшифровкой и стоп-кадрами.
/// Делается на телефоне и отдаётся в «Поделиться» (мессенджер, почта, диск).
class ScanReport {
  static Future<void> share(AppState app, AppLocalizations t, List<EcuResult> results) async {
    final file = await build(app, t, results);
    await SharePlus.instance.share(ShareParams(files: [XFile(file.path, mimeType: 'application/pdf')], subject: t.reportTitle));
  }

  static Future<File> build(AppState app, AppLocalizations t, List<EcuResult> results) async {
    final lang = app.lang;
    final regular = pw.Font.ttf(await rootBundle.load('assets/google_fonts/IBMPlexSans-Regular.ttf'));
    final bold = pw.Font.ttf(await rootBundle.load('assets/google_fonts/IBMPlexSans-Bold.ttf'));
    final mono = pw.Font.ttf(await rootBundle.load('assets/google_fonts/IBMPlexMono-Regular.ttf'));
    final now = DateTime.now();
    String two(int v) => v.toString().padLeft(2, '0');
    final date = '${two(now.day)}.${two(now.month)}.${now.year} ${two(now.hour)}:${two(now.minute)}';

    // стоп-кадры подтягиваем сразу, чтобы они были в отчёте
    final snaps = <String, List<String>>{};
    for (final r in results.where((r) => r.answered && r.dtcs.isNotEmpty)) {
      for (final d in r.dtcs) {
        try {
          final s = await app.diag!.readSnapshot(r.def, d);
          snaps['${r.def.tx}:${d.code}'] = [
            for (final (item, v) in s)
              '${item.nameFor(lang)} ${v.toStringAsFixed(item.decimals).replaceAll('.', ',')} ${liveUnit(item.unit, t, lang)}'
          ];
        } catch (_) {}
      }
    }

    final answered = results.where((r) => r.answered).toList();
    final faults = answered.fold<int>(0, (n, r) => n + r.dtcs.length);
    const ink = PdfColor.fromInt(0xFF0F172A);
    const dim = PdfColor.fromInt(0xFF475569);
    const red = PdfColor.fromInt(0xFFBE185D);
    const green = PdfColor.fromInt(0xFF15803D);
    const line = PdfColor.fromInt(0xFFE2E8F0);

    pw.Widget kv(String k, String v) => pw.Padding(
          padding: const pw.EdgeInsets.only(bottom: 2),
          child: pw.Row(children: [
            pw.SizedBox(width: 90, child: pw.Text(k, style: pw.TextStyle(color: dim, fontSize: 10))),
            pw.Expanded(child: pw.Text(v, style: const pw.TextStyle(fontSize: 10))),
          ]),
        );

    final doc = pw.Document(theme: pw.ThemeData.withFont(base: regular, bold: bold));
    doc.addPage(pw.MultiPage(
      pageFormat: PdfPageFormat.a4,
      margin: const pw.EdgeInsets.fromLTRB(36, 36, 36, 40),
      footer: (c) => pw.Row(children: [
        pw.Text(t.reportFooter, style: pw.TextStyle(color: dim, fontSize: 8)),
        pw.Spacer(),
        pw.Text('${c.pageNumber}/${c.pagesCount}', style: pw.TextStyle(color: dim, fontSize: 8)),
      ]),
      build: (c) => [
        pw.Container(
          padding: const pw.EdgeInsets.all(14),
          decoration: pw.BoxDecoration(
            gradient: const pw.LinearGradient(colors: [PdfColor.fromInt(0xFF0E7490), PdfColor.fromInt(0xFF6D28D9)]),
            borderRadius: pw.BorderRadius.circular(10),
          ),
          child: pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
            pw.Text(t.reportTitle, style: pw.TextStyle(color: PdfColors.white, fontSize: 18, fontWeight: pw.FontWeight.bold)),
            pw.SizedBox(height: 2),
            pw.Text('${app.car.name}${app.car.sub.isEmpty ? '' : ' · ${app.car.sub}'}',
                style: const pw.TextStyle(color: PdfColors.white, fontSize: 12)),
          ]),
        ),
        pw.SizedBox(height: 12),
        kv(t.reportDate, date),
        if (app.vin != null) kv(t.vin, app.vin!),
        kv(t.battery, t.volts(app.batteryText)),
        if (app.fw.isNotEmpty) kv(t.firmware, app.fw),
        pw.SizedBox(height: 10),
        pw.Text('${t.modules}: ${answered.length}/${results.length} · ${t.faultCount(faults)}',
            style: pw.TextStyle(fontSize: 12, fontWeight: pw.FontWeight.bold, color: faults > 0 ? red : green)),
        pw.SizedBox(height: 10),
        for (final r in results)
          pw.Container(
            margin: const pw.EdgeInsets.only(bottom: 8),
            padding: const pw.EdgeInsets.all(10),
            decoration: pw.BoxDecoration(
              border: pw.Border.all(color: r.dtcs.isNotEmpty ? red : line),
              borderRadius: pw.BorderRadius.circular(8),
            ),
            child: pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
              pw.Row(children: [
                pw.Text(r.def.nameFor(lang), style: pw.TextStyle(fontSize: 12, fontWeight: pw.FontWeight.bold, color: ink)),
                pw.SizedBox(width: 8),
                pw.Text('${r.def.tx.toRadixString(16).toUpperCase()} → ${r.def.rx.toRadixString(16).toUpperCase()}',
                    style: pw.TextStyle(font: mono, fontSize: 9, color: dim)),
                pw.Spacer(),
                pw.Text(
                  !r.answered ? t.noAnswer : t.faultCount(r.dtcs.length),
                  style: pw.TextStyle(fontSize: 10, color: !r.answered ? dim : (r.dtcs.isEmpty ? green : red)),
                ),
              ]),
              for (final d in r.dtcs) ...[
                pw.SizedBox(height: 6),
                pw.Row(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
                  pw.SizedBox(width: 52, child: pw.Text(d.code, style: pw.TextStyle(font: mono, fontSize: 10, color: ink))),
                  pw.Expanded(
                    child: pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
                      pw.Text(app.kb?.dtcText(d.code, lang) ?? t.unknownFault, style: const pw.TextStyle(fontSize: 10)),
                      if (snaps['${r.def.tx}:${d.code}']?.isNotEmpty ?? false)
                        pw.Text('${t.freezeFrame}: ${snaps['${r.def.tx}:${d.code}']!.join(' · ')}',
                            style: pw.TextStyle(fontSize: 8.5, color: dim)),
                    ]),
                  ),
                  pw.Text(d.active ? t.faultActive : t.faultStored,
                      style: pw.TextStyle(fontSize: 9, color: d.active ? red : dim)),
                ]),
              ],
            ]),
          ),
      ],
    ));

    final dir = await getTemporaryDirectory();
    final stamp = '${now.year}${two(now.month)}${two(now.day)}_${two(now.hour)}${two(now.minute)}';
    final file = File('${dir.path}/OBD_${(app.vin ?? 'car').replaceAll(RegExp(r'[^A-Za-z0-9]'), '')}_$stamp.pdf');
    await file.writeAsBytes(await doc.save());
    return file;
  }
}
