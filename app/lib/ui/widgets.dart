import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme.dart';

/// Плашка со свечением (в яркой теме) или мягкая карточка (в инженерной).
class GlowCard extends StatelessWidget {
  const GlowCard({super.key, required this.child, this.tint, this.padding = const EdgeInsets.all(16), this.onTap});
  final Widget child;
  final Color? tint;
  final EdgeInsets padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final t = tint ?? p.accent;
    final card = Container(
      padding: padding,
      decoration: BoxDecoration(
        color: p.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: p.isBright ? t.withValues(alpha: 0.35) : p.border),
        boxShadow: p.cardShadow(t),
      ),
      child: child,
    );
    if (onTap == null) return card;
    return InkWell(borderRadius: BorderRadius.circular(18), onTap: onTap, child: card);
  }
}

/// Круглый стрелочный прибор как в макете «Датчики».
class Gauge extends StatelessWidget {
  const Gauge({
    super.key,
    required this.value,
    required this.min,
    required this.max,
    required this.label,
    required this.unit,
    this.redFrom,
    this.size = 150,
    this.color,
    this.decimals = 0,
  });

  final double value, min, max;
  final String label, unit;
  final double? redFrom;
  final double size;
  final Color? color;
  final int decimals; // знаков после запятой: напряжению нужен 1

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final c = color ?? p.gaugeA;
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _GaugePainter(
          value: value.clamp(min, max),
          min: min,
          max: max,
          redFrom: redFrom,
          color: c,
          track: p.border,
          tick: p.textDim,
          needle: p.bad,
          hub: p.surface,
        ),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // цифра ниже оси стрелки, чтобы стрелка её не перечёркивала
              SizedBox(height: size * 0.5),
              Text(value.isNaN ? '—' : value.toStringAsFixed(decimals).replaceAll('.', ','),
                  style: display(context, size * 0.15)),
              Text(unit, style: TextStyle(color: p.textDim, fontSize: size * 0.075)),
            ],
          ),
        ),
      ),
    );
  }
}

class _GaugePainter extends CustomPainter {
  _GaugePainter({
    required this.value,
    required this.min,
    required this.max,
    required this.redFrom,
    required this.color,
    required this.track,
    required this.tick,
    required this.needle,
    required this.hub,
  });

  final double value, min, max;
  final double? redFrom;
  final Color color, track, tick, needle, hub;

  static const startDeg = 135.0, sweepDeg = 270.0;

  double _ang(double v) => (startDeg + sweepDeg * (v - min) / (max - min)) * math.pi / 180;

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.width / 2 - 8;
    final rect = Rect.fromCircle(center: c, radius: r);
    final s = math.pi * startDeg / 180;
    final sweep = math.pi * sweepDeg / 180;

    canvas.drawArc(rect, s, sweep, false,
        Paint()..style = PaintingStyle.stroke..strokeWidth = r * 0.08..strokeCap = StrokeCap.round..color = track);

    if (redFrom != null) {
      final rs = _ang(redFrom!);
      canvas.drawArc(rect, rs, _ang(max) - rs, false,
          Paint()..style = PaintingStyle.stroke..strokeWidth = r * 0.08..color = const Color(0xFFF43F5E));
    }

    canvas.drawArc(rect, s, _ang(value) - s, false,
        Paint()..style = PaintingStyle.stroke..strokeWidth = r * 0.08..strokeCap = StrokeCap.round..color = color);

    // деления
    final tp = Paint()..color = tick..strokeWidth = 2..strokeCap = StrokeCap.round;
    for (var i = 0; i <= 8; i++) {
      final a = (startDeg + sweepDeg * i / 8) * math.pi / 180;
      final o = Offset(math.cos(a), math.sin(a));
      canvas.drawLine(c + o * (r - r * 0.14), c + o * (r - r * 0.22), tp);
    }

    // стрелка
    if (!value.isNaN) {
      final a = _ang(value);
      final dir = Offset(math.cos(a), math.sin(a));
      final perp = Offset(-dir.dy, dir.dx);
      final tip = c + dir * (r * 0.78);
      final b1 = c + perp * 3, b2 = c - perp * 3;
      canvas.drawPath(
          Path()..moveTo(b1.dx, b1.dy)..lineTo(tip.dx, tip.dy)..lineTo(b2.dx, b2.dy)..close(),
          Paint()..color = needle);
    }
    canvas.drawCircle(c, r * 0.08, Paint()..color = hub);
    canvas.drawCircle(c, r * 0.08, Paint()..style = PaintingStyle.stroke..strokeWidth = 2..color = needle);
  }

  @override
  bool shouldRepaint(_GaugePainter old) => old.value != value || old.color != color;
}

/// Цветной бейдж-«таблетка».
class Pill extends StatelessWidget {
  const Pill(this.text, {super.key, required this.fg, required this.bg});
  final String text;
  final Color fg, bg;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
        child: Text(text, style: TextStyle(color: fg, fontSize: 13, fontWeight: FontWeight.w600)),
      );
}

/// График значения за последнее время: линия + мягкая заливка под ней.
class Sparkline extends CustomPainter {
  Sparkline(this.points, this.min, this.max, this.color, this.grid);
  final List<double> points;
  final double min, max;
  final Color color, grid;

  @override
  void paint(Canvas canvas, Size size) {
    final gp = Paint()..color = grid..strokeWidth = 1;
    for (var i = 0; i <= 2; i++) {
      final y = size.height * i / 2;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gp);
    }
    final pts = points.where((v) => !v.isNaN).toList();
    if (pts.length < 2) return;
    const maxPoints = 150;
    final dx = size.width / (maxPoints - 1);
    final x0 = size.width - dx * (pts.length - 1);
    double y(double v) => size.height - ((v - min) / (max - min)).clamp(0.0, 1.0) * size.height;
    final line = Path()..moveTo(x0, y(pts.first));
    for (var i = 1; i < pts.length; i++) {
      line.lineTo(x0 + dx * i, y(pts[i]));
    }
    final fill = Path.from(line)
      ..lineTo(size.width, size.height)
      ..lineTo(x0, size.height)
      ..close();
    canvas.drawPath(
        fill,
        Paint()
          ..shader = LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [color.withValues(alpha: 0.35), color.withValues(alpha: 0.0)],
          ).createShader(Offset.zero & size));
    canvas.drawPath(
        line,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.2
          ..strokeJoin = StrokeJoin.round);
  }

  @override
  bool shouldRepaint(Sparkline old) => true;
}

/// Несколько линий на одном графике (главный график «Датчиков»). У каждой своя шкала
/// (min..max её датчика): обороты и температура в одних единицах не сравнить.
class MultiSparkline extends CustomPainter {
  MultiSparkline(this.series, this.grid);
  final List<(List<double>, double, double, Color)> series;
  final Color grid;

  @override
  void paint(Canvas canvas, Size size) {
    final gp = Paint()..color = grid..strokeWidth = 1;
    for (var i = 0; i <= 4; i++) {
      final y = size.height * i / 4;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gp);
    }
    const maxPoints = 150;
    final dx = size.width / (maxPoints - 1);
    for (final (points, min, max, color) in series) {
      final pts = points.where((v) => !v.isNaN).toList();
      if (pts.length < 2) continue;
      final x0 = size.width - dx * (pts.length - 1);
      double y(double v) => size.height - ((v - min) / (max - min)).clamp(0.0, 1.0) * size.height;
      final line = Path()..moveTo(x0, y(pts.first));
      for (var i = 1; i < pts.length; i++) {
        line.lineTo(x0 + dx * i, y(pts[i]));
      }
      canvas.drawPath(
          line,
          Paint()
            ..color = color
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2.4
            ..strokeJoin = StrokeJoin.round);
    }
  }

  @override
  bool shouldRepaint(MultiSparkline old) => true;
}

class NavItem {
  const NavItem(this.icon, this.label, this.color);
  final IconData icon;
  final String label;
  final Color color;
}

/// Нижнее меню из цветных плашек: у каждого раздела свой цвет,
/// открытый раздел залит градиентом и светится.
class GlowNavBar extends StatelessWidget {
  const GlowNavBar({super.key, required this.index, required this.onTap, required this.items});
  final int index;
  final ValueChanged<int> onTap;
  final List<NavItem> items;

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    return Container(
      color: p.bg,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
          child: Row(
            children: [
              for (var i = 0; i < items.length; i++) ...[
                if (i > 0) const SizedBox(width: 8),
                Expanded(child: _item(context, items[i], i == index, () => onTap(i))),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _item(BuildContext context, NavItem it, bool on, VoidCallback tap) {
    final p = context.p;
    final c = it.color;
    final dark = Color.lerp(c, Colors.black, 0.35)!;
    return GestureDetector(
      onTap: tap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        height: 62,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          color: on ? null : p.surface,
          gradient: on ? LinearGradient(colors: [c, dark], begin: Alignment.topLeft, end: Alignment.bottomRight) : null,
          border: Border.all(color: on ? Colors.transparent : c.withValues(alpha: 0.35)),
          boxShadow: [
            BoxShadow(
              color: c.withValues(alpha: on ? 0.5 : (p.isBright ? 0.18 : 0.0)),
              blurRadius: on ? 18 : 12,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(it.icon, size: 24, color: on ? Colors.white : c),
            const SizedBox(height: 3),
            Text(
              it.label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 12,
                fontWeight: on ? FontWeight.w700 : FontWeight.w500,
                color: on ? Colors.white : p.text,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Яркая кнопка-плашка: градиент, значок, свечение (как «Автоскан»).
class GradientButton extends StatelessWidget {
  const GradientButton({
    super.key,
    required this.icon,
    required this.label,
    required this.colors,
    required this.onPressed,
    this.busy = false,
  });
  final IconData icon;
  final String label;
  final List<Color> colors;
  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final off = onPressed == null || busy;
    final radius = BorderRadius.circular(18);
    return Opacity(
      opacity: off ? 0.55 : 1,
      child: Container(
        height: 56,
        decoration: BoxDecoration(
          borderRadius: radius,
          gradient: LinearGradient(colors: colors),
          boxShadow: [BoxShadow(color: colors.last.withValues(alpha: 0.45), blurRadius: 20, offset: const Offset(0, 8))],
        ),
        child: Material(
          type: MaterialType.transparency,
          child: InkWell(
            borderRadius: radius,
            onTap: off ? null : onPressed,
            child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              busy
                  ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white))
                  : Icon(icon, color: Colors.white, size: 24),
              const SizedBox(width: 10),
              Text(label, style: display(context, 17, w: FontWeight.w700).copyWith(color: Colors.white)),
            ]),
          ),
        ),
      ),
    );
  }
}

class FolderTab {
  const FolderTab(this.label, this.icon, this.color);
  final String label;
  final IconData icon;
  final Color color;
}

/// Вкладки-ярлычки, как у папки: активная выше, залита своим цветом и переходит
/// в полосу над страницей; остальные ниже и приглушены, каждая своего цвета.
class FolderTabs extends StatelessWidget implements PreferredSizeWidget {
  const FolderTabs({super.key, required this.controller, required this.tabs});
  final TabController controller;
  final List<FolderTab> tabs;

  @override
  Size get preferredSize => const Size.fromHeight(62);

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final sel = controller.index;
        final active = tabs[sel].color;
        return Column(mainAxisSize: MainAxisSize.min, children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              for (var i = 0; i < tabs.length; i++) ...[
                if (i > 0) const SizedBox(width: 5),
                Expanded(child: _tab(context, tabs[i], i == sel, () => controller.animateTo(i))),
              ],
            ]),
          ),
          // край «страницы» — полоса цвета активной вкладки
          AnimatedContainer(duration: const Duration(milliseconds: 200), height: 4, color: active),
          Container(height: 1, color: p.bg),
        ]);
      },
    );
  }

  Widget _tab(BuildContext context, FolderTab tab, bool on, VoidCallback onTap) {
    final p = context.p;
    final c = tab.color;
    final dark = Color.lerp(c, Colors.black, 0.25)!;
    final dim = p.isBright ? Color.lerp(c, Colors.white, 0.78)! : Color.lerp(c, p.bg, 0.72)!;
    final textDim = p.isBright ? Color.lerp(c, Colors.black, 0.35)! : Color.lerp(c, Colors.white, 0.25)!;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        height: on ? 52 : 42,
        decoration: BoxDecoration(
          gradient: on ? LinearGradient(colors: [c, dark], begin: Alignment.topCenter, end: Alignment.bottomCenter) : null,
          color: on ? null : dim,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(14)),
          boxShadow: on ? [BoxShadow(color: c.withValues(alpha: 0.45), blurRadius: 12, offset: const Offset(0, -2))] : null,
        ),
        child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(tab.icon, size: on ? 18 : 16, color: on ? Colors.white : textDim),
          const SizedBox(width: 5),
          Flexible(
            child: Text(
              tab.label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: on ? 14 : 13,
                fontWeight: on ? FontWeight.w700 : FontWeight.w600,
                color: on ? Colors.white : textDim,
              ),
            ),
          ),
        ]),
      ),
    );
  }
}
