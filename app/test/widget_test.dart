import 'package:flutter_test/flutter_test.dart';

import 'package:scaner_app/transport/uds.dart';

void main() {
  test('DTC byte decoding', () {
    expect(Dtc([0xC1, 0x00, 0x00], 0x08).code, 'U0100');
    expect(Dtc([0x01, 0x30, 0x00], 0x09).code, 'P0130');
    expect(Dtc([0x01, 0x30, 0x00], 0x09).active, true);
    expect(Dtc([0xC1, 0x00, 0x00], 0x08).active, false);
  });
}
