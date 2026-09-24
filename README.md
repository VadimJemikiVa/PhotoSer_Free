# PhotoSer Free

PhotoSer Free is a Windows desktop application for transferring files from a phone to a computer over a local network.

**Copyright (C) 2026 JemikiVa**

## Русский

### Что это

PhotoSer Free позволяет передавать файлы **с телефона на компьютер** через локальную сеть.

Публичная Free-версия является **односторонней**:
- телефон → компьютер;
- скачивание файлов с компьютера на телефон в Free-версии не предусмотрено;
- подключение защищается PIN-кодом, если PIN включён;
- QR-код помогает открыть адрес PhotoSer на телефоне;
- приложение рассчитано на использование в локальной сети.


### Ограничение передачи

Максимальный общий размер одной передачи в Free-версии — **2 GiB (2 × 1024³ байт)**.

Превышение этого ограничения должно отображаться как ошибка лимита передачи, а не как обычная ошибка соединения.

### Порты

По умолчанию используется порт **51773**.

Доступны резервные порты:
- 51774
- 51775
- 8080
- 8888
- 5000

Также порт можно указать вручную в диапазоне **1–65535**. Выбранный порт сохраняется в `photoser_settings.json`.

### Языки

Интерфейс PhotoSer поддерживает:
- русский;
- English;
- latviešu;
- Deutsch.

### Лицензия

PhotoSer Free распространяется по **GNU General Public License, version 3 (GPLv3)**.

Полный текст лицензии находится в файле `LICENSE`.

Программа распространяется в надежде, что она будет полезной, но **БЕЗ КАКИХ-ЛИБО ГАРАНТИЙ** в пределах, разрешённых GPLv3.

### Сторонние компоненты

PhotoSer использует стороннее программное обеспечение. Его лицензии и ссылки на соответствующие проекты перечислены в `THIRD-PARTY-NOTICES.txt`.

### Сборка из исходников

Для сборки Windows-версии используются:
- Python;
- PyInstaller;
- Inno Setup (для установщика).

Файлы для сборки находятся в корне проекта:
- `PhotoSer_Free.py` — исходный код;
- `PhotoSer.spec` — конфигурация PyInstaller;
- `PhotoSer.iss` — скрипт Inno Setup;
- `build_photoser.bat` — автоматизация сборки;
- `photoser_app_icon.ico` — иконка;
- `version_info.txt` — сведения о версии;
- `requirements.txt` — Python-зависимости проекта.

`build_photoser.bat` сначала создаёт `dist\PhotoSer.exe`, а затем, если `ISCC.exe` доступен в PATH, создаёт установщик в `installer-output\`.

### Запуск исходников

Установите зависимости из `requirements.txt`, затем запустите:

```text
python PhotoSer_Free.py
```

### Распространение

При распространении PhotoSer сохраняйте вместе с программой:
- `README.md`;
- `LICENSE`;
- `THIRD-PARTY-NOTICES.txt`;
- соответствующий исходный код и необходимые файлы сборки.

Этот проект не добавляет к GPLv3 отдельных ограничений «только для домашнего использования», «только для некоммерческого использования» или запрета на дальнейшее распространение.

Обратная связь.
Если вы нашли ошибку, хотите предложить улучшение или задать вопрос, создайте Issue в репозитории GitHub или напишите на jemiki@inbox.lv.
---

## English

### What it is

PhotoSer Free is a Windows desktop application for transferring files **from a phone to a computer** over a local network.

The public Free edition is **one-way**:
- phone → computer;
- downloading files from the computer to the phone is not provided in the Free edition;
- PIN authentication can be required;
- a QR code helps open the PhotoSer address on the phone;
- the application is intended for use on a local network.

### Transfer limit

The maximum total size of one transfer in the Free edition is **2 GiB (2 × 1024³ bytes)**.

Exceeding this limit is reported as a transfer-limit error, separately from connection/network errors.

### Ports

The default port is **51773**.

Fallback ports:
- 51774
- 51775
- 8080
- 8888
- 5000

A port may also be entered manually in the range **1–65535**. The selected port is saved in `photoser_settings.json`.

### Languages

The interface supports:
- Russian;
- English;
- Latvian;
- German.

### License

PhotoSer Free is distributed under the **GNU General Public License, version 3 (GPLv3)**.

The complete license text is provided in `LICENSE`.

The program is distributed in the hope that it will be useful, but **WITHOUT ANY WARRANTY** to the extent permitted by the GPLv3.

### Third-party components

PhotoSer uses third-party software. Their licenses and project references are listed in `THIRD-PARTY-NOTICES.txt`.

### Building from source

The Windows build uses:
- Python;
- PyInstaller;
- Inno Setup (for the installer).

Build files are kept in the project root:
- `PhotoSer_Free.py` — source code;
- `PhotoSer.spec` — PyInstaller configuration;
- `PhotoSer.iss` — Inno Setup script;
- `build_photoser.bat` — build automation;
- `photoser_app_icon.ico` — application icon;
- `version_info.txt` — version information;
- `requirements.txt` — Python dependencies.

`build_photoser.bat` first creates `dist\PhotoSer.exe` and, when `ISCC.exe` is available in PATH, creates the installer in `installer-output\`.

### Running from source

Install the dependencies from `requirements.txt`, then run:

```text
python PhotoSer_Free.py
```

### Distribution

When distributing PhotoSer, keep the following with the program where practical:
- `README.md`;
- `LICENSE`;
- `THIRD-PARTY-NOTICES.txt`;
- the corresponding source code and necessary build information.

This project does not add separate "home use only", "non-commercial use only", or "no redistribution" restrictions on top of the GPLv3.

Feedback 
If you find a bug, have a suggestion, or have a question, please open an Issue in the GitHub repository or contact us at jemiki@inbox.lv.
---

## Latviešu

PhotoSer Free ir Windows darbvirsmas lietotne failu pārsūtīšanai **no tālruņa uz datoru** lokālajā tīklā.

Publiskā Free versija ir **vienvirziena**:
- tālrunis → dators;
- failu lejupielāde no datora uz tālruni Free versijā nav paredzēta;
- var pieprasīt PIN kodu;
- QR kods palīdz tālrunī atvērt PhotoSer adresi;
- lietotne ir paredzēta lietošanai lokālajā tīklā.

Vienas pārsūtīšanas maksimālais kopējais izmērs ir **2 GiB**.

Noklusējuma ports ir **51773**. Pieejami arī 51774, 51775, 8080, 8888 un 5000, kā arī manuāla porta ievade diapazonā 1–65535. Izvēlētais ports tiek saglabāts `photoser_settings.json`.

Interfeiss atbalsta krievu, angļu, latviešu un vācu valodu.

PhotoSer Free tiek izplatīts saskaņā ar **GNU General Public License, 3. versiju (GPLv3)**. Pilns licences teksts ir failā `LICENSE`. Trešo pušu komponentes un to licences ir norādītas failā `THIRD-PARTY-NOTICES.txt`.

Atsauksmes 
Ja atrodat kļūdu, jums ir ieteikums vai jautājums, lūdzu, izveidojiet Issue GitHub repozitorijā vai rakstiet uz jemiki@inbox.lv.
---

## Deutsch

PhotoSer Free ist eine Windows-Desktopanwendung zur Dateiübertragung **vom Telefon zum Computer** über ein lokales Netzwerk.

Die öffentliche Free-Version ist **einseitig**:
- Telefon → Computer;
- das Herunterladen von Dateien vom Computer auf das Telefon ist in der Free-Version nicht vorgesehen;
- eine PIN-Authentifizierung kann verlangt werden;
- ein QR-Code hilft beim Öffnen der PhotoSer-Adresse auf dem Telefon;
- die Anwendung ist für die Verwendung in einem lokalen Netzwerk vorgesehen.

Die maximale Gesamtgröße einer Übertragung beträgt **2 GiB**.

Der Standardport ist **51773**. Zusätzlich stehen 51774, 51775, 8080, 8888 und 5000 sowie eine manuelle Eingabe im Bereich 1–65535 zur Verfügung. Der gewählte Port wird in `photoser_settings.json` gespeichert.

Die Benutzeroberfläche unterstützt Russisch, Englisch, Lettisch und Deutsch.

PhotoSer Free wird unter der **GNU General Public License, Version 3 (GPLv3)** verteilt. Der vollständige Lizenztext befindet sich in `LICENSE`. Die Lizenzen der 
Drittanbieter-Komponenten sind in `THIRD-PARTY-NOTICES.txt` aufgeführt.

Rückmeldung
Wenn Sie einen Fehler finden, einen Verbesserungsvorschlag haben oder eine Frage stellen möchten, erstellen Sie bitte ein Issue im GitHub-Repository oder schreiben Sie an jemiki@inbox.lv.
---

## Author / Автор / Autors / Autor

**JemikiVa**

## Project contents

The repository contains the source code and build configuration needed to reproduce the Windows application and installer. The exact dependency versions used for a particular binary release should be recorded when the binary is built.
