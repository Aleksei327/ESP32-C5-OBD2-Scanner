import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Две темы из макетов: «Инженерная» (тёмная) и «Яркая» (светлая, цветная).
enum AppThemeKind { engineering, bright }

class AppPalette {
  const AppPalette({
    required this.bg,
    required this.surface,
    required this.border,
    required this.text,
    required this.textDim,
    required this.accent,
    required this.onAccent,
    required this.good,
    required this.bad,
    required this.info,
    required this.gaugeA,
    required this.gaugeB,
    required this.glow,
  });

  final Color bg, surface, border, text, textDim;
  final Color accent, onAccent, good, bad, info, gaugeA, gaugeB;
  final double glow; // сила свечения плашек, 0 в инженерной теме

  static const engineering = AppPalette(
    bg: Color(0xFF111417),
    surface: Color(0xFF1A1F24),
    border: Color(0xFF2A3138),
    text: Color(0xFFE8EAED),
    textDim: Color(0xFFA7B0B9),
    accent: Color(0xFFF2B33D),
    onAccent: Color(0xFF1A1305),
    good: Color(0xFF4CC38A),
    bad: Color(0xFFFF6B5A),
    info: Color(0xFF6CB6FF),
    gaugeA: Color(0xFFF2B33D),
    gaugeB: Color(0xFF8B5CF6),
    glow: 0.0,
  );

  static const bright = AppPalette(
    bg: Color(0xFFF4F6FB),
    surface: Color(0xFFFFFFFF),
    border: Color(0x140F172A),
    text: Color(0xFF0F172A),
    textDim: Color(0xFF475569),
    accent: Color(0xFF0E7490),
    onAccent: Color(0xFFFFFFFF),
    good: Color(0xFF16A34A),
    bad: Color(0xFFBE185D),
    info: Color(0xFF6D28D9),
    gaugeA: Color(0xFF06B6D4),
    gaugeB: Color(0xFF8B5CF6),
    glow: 1.0,
  );

  static AppPalette of(AppThemeKind k) =>
      k == AppThemeKind.bright ? bright : engineering;

  bool get isBright => glow > 0;

  /// Тень-свечение для цветных плашек (в яркой теме), иначе обычная мягкая тень.
  List<BoxShadow> cardShadow(Color tint) => isBright
      ? [BoxShadow(color: tint.withValues(alpha: 0.35), blurRadius: 24, offset: const Offset(0, 12))]
      : const [];
}

ThemeData buildTheme(AppThemeKind kind) {
  final p = AppPalette.of(kind);
  final base = p.isBright ? ThemeData.light() : ThemeData.dark();
  final scheme = (p.isBright ? const ColorScheme.light() : const ColorScheme.dark()).copyWith(
    surface: p.bg,
    primary: p.accent,
    onPrimary: p.onAccent,
    error: p.bad,
  );
  return base.copyWith(
    scaffoldBackgroundColor: p.bg,
    colorScheme: scheme,
    textTheme: GoogleFonts.ibmPlexSansTextTheme(base.textTheme).apply(
      bodyColor: p.text,
      displayColor: p.text,
    ),
    extensions: [AppPaletteExt(p)],
  );
}

/// Доступ к палитре через Theme.of(context).extension.
class AppPaletteExt extends ThemeExtension<AppPaletteExt> {
  const AppPaletteExt(this.palette);
  final AppPalette palette;
  @override
  ThemeExtension<AppPaletteExt> copyWith() => this;
  @override
  ThemeExtension<AppPaletteExt> lerp(ThemeExtension<AppPaletteExt>? other, double t) => this;
}

extension PaletteContext on BuildContext {
  AppPalette get p => Theme.of(this).extension<AppPaletteExt>()!.palette;
}

/// Заголовочный шрифт как в макетах (Exo 2).
TextStyle display(BuildContext ctx, double size, {FontWeight w = FontWeight.w800}) =>
    GoogleFonts.exo2(fontSize: size, fontWeight: w, color: ctx.p.text, letterSpacing: -0.2);

TextStyle mono(BuildContext ctx, double size, {Color? color}) =>
    GoogleFonts.ibmPlexMono(fontSize: size, color: color ?? ctx.p.text);
