# Авторские права и условия использования

(c) 2026 Алексей Субботин. Все права, кроме перечисленных ниже, сохранены за автором.

*(English version below / Английская версия ниже)*

## На что распространяется

Всё опубликованное в этом репозитории — документация, схема и плата KiCad, экспорт в PDF, библиотеки посадочных мест и 3D-модели, скрипты-генераторы, исходники приложения (`app/`), симулятора (`sim/`) и прошивки (`firmware/`) — распространяется по лицензии [Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International](LICENSE) (CC BY-NC-ND 4.0).

Коротко: читать, изучать и делиться со ссылкой на автора можно; использовать в коммерческих целях и публиковать переделанные версии — нельзя.

## Отдельное разрешение: собрать одну штуку для себя

Несмотря на условие NoDerivatives, вам **прямо разрешается собрать один экземпляр устройства для личного некоммерческого использования** и вносить в конструкцию изменения в той мере, в какой это для этого нужно.

## Что требует письменного разрешения

- продажа конструкции, чистых плат, наборов для сборки или готовых устройств;
- использование конструкции или любой узнаваемой её части в продукте или услуге, предлагаемых за деньги;
- публикация переделанных версий этих файлов и их распространение как собственной работы;
- любое иное коммерческое использование.

## Программы

Сейчас в репозитории только исходники: приложение Flutter, симулятор на Python и прошивка самотеста на ESP-IDF. Собранных программ здесь нет. Чужого кода в них не скопировано; библиотеки, от которых они зависят (Flutter и пакеты pub.dev, ESP-IDF, websockets), скачиваются при сборке и остаются под своими лицензиями.

Если в будущую прошивку адаптера войдёт код открытых проектов под GPL-3.0 (например, [ludwig-v/arduino-psa-diag](https://github.com/ludwig-v/arduino-psa-diag)), эта часть будет распространяться под GPL-3.0, как того требует их лицензия, и это будет указано рядом с ней.

## Сторонние материалы

- Шрифты Exo 2 и IBM Plex в `app/assets/google_fonts/` — под SIL Open Font License 1.1, тексты лицензий лежат рядом.
- Посадочные места и 3D-модели из стандартных библиотек KiCad — под их лицензией (CC BY-SA 4.0 с исключением для плат).
- Сведения о протоколах и адресах блоков PSA взяты из открытых источников, ссылки приведены в документации; список — в разделе «Благодарности и сторонние проекты» в [README.ru.md](README.ru.md).
- Фотографии покупных модулей в репозиторий не входят: на них права продавцов.

## Контакты

Алексей Субботин — https://github.com/Aleksei327

---

# Copyright and terms of use

Copyright (c) 2026 Aleksei Subbotin. All rights not granted below are reserved.

## What this covers

Everything published in this repository — documentation, KiCad schematic and board, PDF exports, footprint libraries and 3D models, generator scripts, and the source code of the app (`app/`), the simulator (`sim/`) and the firmware (`firmware/`) — is licensed under [Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International](LICENSE) (CC BY-NC-ND 4.0).

In short: read it, study it, share it with credit to the author, but do not use it commercially and do not publish modified versions.

## Additional permission: build one for yourself

Notwithstanding the NoDerivatives condition of the license, you are explicitly permitted to **build a single unit of this device for your own private, non-commercial use**, and to adapt the design as far as necessary to do so.

## What requires written permission

- selling this design, bare boards, kits, or assembled units;
- using the design, or any recognisable part of it, in a product or service offered for sale;
- publishing modified versions of these files or redistributing them as your own work;
- any other commercial use.

## Software

The repository contains source code only: the Flutter app, the Python simulator and the ESP-IDF self-test firmware. No built binaries are published. No third-party code is copied into them; the libraries they depend on (Flutter and pub.dev packages, ESP-IDF, websockets) are downloaded at build time and remain under their own licenses.

If the future adapter firmware includes code from open-source projects licensed under GPL-3.0 (for example [ludwig-v/arduino-psa-diag](https://github.com/ludwig-v/arduino-psa-diag)), that part will be distributed under GPL-3.0 as their license requires, and this will be stated next to it.

## Third-party material

- The Exo 2 and IBM Plex fonts in `app/assets/google_fonts/` are under the SIL Open Font License 1.1; the license texts are included next to them.
- Footprints and 3D models from the standard KiCad libraries are under their own license (CC BY-SA 4.0 with an exception for boards).
- Information about PSA protocols and ECU addresses comes from public sources linked in the documentation; see "Credits and third-party work" in [README.md](README.md).
- Photos of purchased modules are not included in this repository: they belong to their sellers.

## Contact

Aleksei Subbotin — https://github.com/Aleksei327
