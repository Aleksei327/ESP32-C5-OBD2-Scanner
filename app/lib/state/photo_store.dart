import 'dart:io';

import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';

/// Фото состояния машины: до [maxPhotos] снимков на машину, в памяти приложения.
/// Папка на машину — по VIN (пока VIN не прочитан — «default»).
class PhotoStore {
  static const maxPhotos = 5;
  final _picker = ImagePicker();

  Future<Directory> _dir(String carKey) async {
    final base = await getApplicationDocumentsDirectory();
    final d = Directory('${base.path}/photos/$carKey');
    if (!d.existsSync()) d.createSync(recursive: true);
    return d;
  }

  Future<List<File>> list(String carKey) async {
    final d = await _dir(carKey);
    final files = d.listSync().whereType<File>().where((f) => f.path.endsWith('.jpg')).toList()
      ..sort((a, b) => a.path.compareTo(b.path));
    return files;
  }

  /// Снять или выбрать фото и сохранить. null — пользователь передумал.
  Future<File?> add(String carKey, {required bool camera}) async {
    if ((await list(carKey)).length >= maxPhotos) return null;
    final x = await _picker.pickImage(
      source: camera ? ImageSource.camera : ImageSource.gallery,
      maxWidth: 2000,
      imageQuality: 85,
    );
    if (x == null) return null;
    final d = await _dir(carKey);
    final name = '${DateTime.now().millisecondsSinceEpoch}.jpg';
    return File(x.path).copy('${d.path}/$name');
  }

  Future<void> remove(File f) async {
    if (f.existsSync()) await f.delete();
  }
}
