# Повний довідник полів MQTT push_status / pushall (Bambu Lab)

Джерело: `device/{DEVICE_ID}/report`, команда `push_status` (надсилається принтером автоматично при зміні стану) або у відповідь на `pushing.pushall`.

Позначення:
- ✅ — вже парситься твоїм ботом (`services/mqtt_message_parser.py`)
- ⭐ — рекомендую додати (реальна практична цінність)
- ⚪ — низький пріоритет / рідко потрібно
- 🔧 — службове/діагностичне

---

## 1. Температури

| Поле | Тип | Опис | Статус |
|---|---|---|---|
| `bed_temper` | float | Поточна температура столу | ✅ |
| `bed_target_temper` | float | Цільова температура столу | ⭐ (показати "нагрівається до X°") |
| `nozzle_temper` | float | Поточна температура сопла | ✅ |
| `nozzle_target_temper` | float | Цільова температура сопла | ⭐ |
| `chamber_temper` | float | Температура камери (X1/H2D) | ⭐ |

## 2. Друк — прогрес і статус

| Поле | Тип | Опис | Статус |
|---|---|---|---|
| `gcode_state` | string | `IDLE`/`RUNNING`/`PAUSE`/`FINISH`/`FAILED` | ✅ |
| `mc_percent` | int | Прогрес друку, % | ✅ |
| `mc_remaining_time` | int | Хвилин лишилось | ✅ |
| `layer_num` | int | Поточний шар | ✅ |
| `total_layer_num` | int | Всього шарів | ✅ |
| `subtask_name` | string | Назва файлу/завдання | ✅ |
| `gcode_file` | string | Ім'я g-code файлу | ⚪ (дублює subtask_name здебільшого) |
| `gcode_start_time` | timestamp | Коли почався друк | ⭐ (для точного обліку часу друку) |
| `gcode_file_prepare_percent` | string | % підготовки файлу перед друком | ⚪ |
| `mc_print_stage` | string | Внутрішня стадія друку | ⚪ 🔧 |
| `mc_print_sub_stage` | int | Підстадія | ⚪ 🔧 |
| `mc_print_error_code` | string | Код помилки друку | ⭐ (окремо від HMS) |
| `print_error` | int | Код помилки (0 = нема) | ⭐ |
| `fail_reason` | string | Причина провалу друку | ⭐ |
| `print_type` | string | Тип завдання (local/cloud/...) | ⚪ |
| `print_gcode_action` | int | Внутрішній код дії | ⚪ 🔧 |
| `print_real_action` | int | Внутрішній код дії | ⚪ 🔧 |
| `queue_number` | int | Позиція в черзі (хмарний друк) | ⚪ |
| `stg` / `stg_cur` | array/int | Список стадій / поточна стадія | ⚪ 🔧 |
| `spd_lvl` | int | Рівень швидкості (1-4) | ✅ |
| `spd_mag` | int | Швидкість, % (100 = норма) | ✅ |
| `home_flag` | int | Бітова маска стану home/калібрування | ⚪ 🔧 |
| `hw_switch_state` | int | Стан кінцевика дверей/кришки | ⭐ (для H2D/X1 з дверима) |

## 3. Вентилятори

| Поле | Тип | Опис | Статус |
|---|---|---|---|
| `cooling_fan_speed` | string | Швидкість part-cooling фена | ⚪ |
| `heatbreak_fan_speed` | string | Швидкість фена хітбрейка | ⚪ |
| `big_fan1_speed` | string | Допоміжний (aux) фен | ⚪ |
| `big_fan2_speed` | string | Фен камери | ⚪ |
| `fan_gear` | int | Бітова маска стану всіх фенів | ⚪ 🔧 |
| `aux_part_fan` | bool | Чи встановлений aux-фен | ⚪ |

## 4. AMS та котушки

| Поле | Тип | Опис | Статус |
|---|---|---|---|
| `ams.ams[].id` | string | ID блоку AMS | ✅ (частково через ams_slots) |
| `ams.ams[].humidity` | string | **Вологість AMS-блоку (1-5)** | ⭐⭐ (для складу/сушки філаменту) |
| `ams.ams[].temp` | string | Температура AMS-блоку | ⭐ |
| `ams.ams[].tray[].id` | string | ID слоту (0-3) | ✅ |
| `tray[].tray_type` | string | Тип пластику (PLA/PETG/...) | ✅ |
| `tray[].tray_color` / `cols` | string | Колір (HEX) | ✅ |
| `tray[].remain` | int | Залишок, % | ✅ |
| `tray[].tray_weight` | string | Вага котушки, г | ✅ |
| `tray[].tag_uid` | string | **RFID UID котушки (Bambu-брендовані)** | ⭐⭐ (автоідентифікація) |
| `tray[].tray_uuid` | string | Унікальний ID партії | ⭐ |
| `tray[].tray_id_name` | string | Назва матеріалу з RFID | ⭐ |
| `tray[].tray_sub_brands` | string | Суббренд | ⚪ |
| `tray[].tray_info_idx` | string | Внутрішній ID профілю (GFA00...) | ⚪ 🔧 |
| `tray[].tray_diameter` | string | Діаметр нитки | ⚪ |
| `tray[].drying_temp` / `drying_time` | string | Рекомендована температура/час сушки | ⭐ (для гігроскопічних матеріалів) |
| `tray[].bed_temp` / `bed_temp_type` | string | Рекомендована температура столу | ⚪ |
| `tray[].nozzle_temp_min/max` | string | Рекомендований діапазон сопла | ⭐ (попередження про невідповідність) |
| `tray[].xcam_info` | string | Дані для AI-калібрування кольору | ⚪ 🔧 |
| `vt_tray` | object | Той самий формат, для зовнішньої котушки (без AMS) | ✅ |
| `tray_now` / `tray_pre` / `tray_tar` | string | Поточний/попередній/цільовий активний слот | ✅ (active_spool_id) |
| `ams_exist_bits` | string | Бітова маска: які AMS-блоки підключені | ⚪ 🔧 |
| `tray_exist_bits` | string | Бітова маска: які слоти заповнені | ⭐ |
| `tray_is_bbl_bits` | string | Бітова маска: які котушки — оригінальні Bambu | ⚪ |
| `tray_read_done_bits` / `tray_reading_bits` | string | Прогрес зчитування RFID | ⚪ 🔧 |
| `ams_rfid_status` | int | Статус RFID-рідера | ⚪ 🔧 |
| `ams_status` | int | Загальний статус AMS | ⭐ |
| `insert_flag` | bool | Чи щойно вставлена котушка | ⚪ |
| `power_on_flag` | bool | AMS увімкнений | ⚪ |
| `filam_bak` | array | Резервні дані філаменту | ⚪ 🔧 |

## 5. HMS-помилки та безпека

| Поле | Тип | Опис | Статус |
|---|---|---|---|
| `hms` | array | **Список активних кодів помилок** | ✅ (парситься, але без розшифровки!) |
| `xcam.spaghetti_detector` | bool | AI-детектор "спагеті" увімкнений | ⭐ |
| `xcam.first_layer_inspector` | bool | Інспекція першого шару увімкнена | ⭐ |
| `xcam.buildplate_marker_detector` | bool | Детектор мітки столу | ⚪ |
| `xcam.printing_monitor` | bool | AI-моніторинг друку увімкнений | ⭐ |
| `xcam.print_halt` | bool | Автозупинка при виявленні проблеми | ⭐ |
| `xcam.halt_print_sensitivity` | string | Чутливість автозупинки (low/medium/high) | ⚪ |
| `xcam.allow_skip_parts` | bool | Чи дозволено пропускати об'єкти | ⚪ |
| `xcam_status` | string | Загальний код статусу AI-камери | ⚪ 🔧 |

## 6. Мережа / залізо / діагностика

| Поле | Тип | Опис | Статус |
|---|---|---|---|
| `wifi_signal` | string | **Сила Wi-Fi сигналу (напр. "-45dBm")** | ⭐⭐ (діагностика обривів) |
| `sdcard` | bool | SD-картка вставлена | ⚪ |
| `nozzle_diameter` | string | Діаметр сопла (0.4/0.6...) | ⭐ |
| `maintain` | int | Внутрішній лічильник обслуговування | ⚪ 🔧 |
| `mess_production_state` | string | Стан виробничого режиму | ⚪ 🔧 |
| `lifecycle` | string | "product" — стадія життєвого циклу | ⚪ 🔧 |
| `online.ahb` / `online.rfid` | bool | Статус допоміжних модулів | ⚪ 🔧 |
| `online.version` | int | Версія протоколу | ⚪ 🔧 |

## 7. Оновлення прошивки

| Поле | Тип | Опис | Статус |
|---|---|---|---|
| `upgrade_state.new_version_state` | int | Чи є нова версія | ⭐ |
| `upgrade_state.ota_new_version_number` | string | Номер нової версії | ⭐ |
| `upgrade_state.force_upgrade` | bool | Обов'язкове оновлення | ⭐ |
| `upgrade_state.status` | string | Статус процесу оновлення | ⚪ |
| `upgrade_state.progress` | string | Прогрес оновлення, % | ⚪ |
| `upgrade_state.err_code` / `message` | - | Помилка оновлення | ⚪ |
| `upgrade_state.consistency_request` | bool | Потрібна перевірка цілісності | ⚪ 🔧 |
| `upgrade_state.module` | string | Який модуль оновлюється | ⚪ 🔧 |
| `ams_new_version_number` / `ahb_new_version_number` | string | Версії прошивок AMS/AHB | ⚪ 🔧 |

## 8. Освітлення

| Поле | Тип | Опис | Статус |
|---|---|---|---|
| `lights_report[].node` | string | `chamber_light` / `work_light` | ✅ (керування є, читання стану — перевір) |
| `lights_report[].mode` | string | `on`/`off`/`flashing` | ✅ |

## 9. Камера / таймлапс

| Поле | Тип | Опис | Статус |
|---|---|---|---|
| `ipcam.ipcam_dev` | string | Чи є камера | ⚪ |
| `ipcam.ipcam_record` | string | Запис відео увімкнено | ⚪ |
| `ipcam.resolution` | string | Роздільна здатність потоку | ⚪ |
| `ipcam.timelapse` | string | Таймлапс увімкнено | ⚪ |

## 10. Завантаження файлу (при відправці на друк)

| Поле | Тип | Опис | Статус |
|---|---|---|---|
| `upload.status` | string | Статус завантаження файлу | ⭐ (прогрес-бар при відправці на друк) |
| `upload.progress` | int | % завантаження | ⭐ |
| `upload.file_size` / `finish_size` | int | Розмір / завантажено байт | ⚪ |
| `upload.speed` | int | Швидкість завантаження | ⚪ |
| `upload.message` | string | Статус-повідомлення ("Good"...) | ⚪ |
| `upload.time_remaining` | int | Скільки лишилось | ⚪ |
| `upload.trouble_id` | string | ID проблеми завантаження | ⚪ |

## 11. Ідентифікатори завдання

| Поле | Тип | Опис | Статус |
|---|---|---|---|
| `subtask_id` | string | ID підзавдання | ⚪ 🔧 |
| `task_id` | string | ID завдання | ⚪ 🔧 |
| `project_id` | string | ID проєкту (хмара) | ⚪ 🔧 |
| `profile_id` | string | ID профілю друку | ⚪ 🔧 |

---

## Рекомендований пріоритет для наступної ітерації парсера (⭐⭐ і ⭐, найцінніші)

1. **`wifi_signal`** — попередження про слабкий сигнал (найкорисніше саме для віддаленого моніторингу).
2. **`ams.ams[].humidity`** — вологість AMS для попередження про псування філаменту.
3. **`tray[].tag_uid` / `tray_uuid` / `tray_id_name`** — RFID-автоідентифікація оригінальних котушок Bambu (синергія зі складом філаменту).
4. **Розшифровка `hms`** — коди вже парсяться, бракує лише словника код→опис (окремий файл, не MQTT-парсинг).
5. **`chamber_temper`, `bed_target_temper`, `nozzle_target_temper`** — повніша картина температур в статусі.
6. **`upgrade_state.new_version_state`/`ota_new_version_number`** — сповіщення про доступне оновлення прошивки.
7. **`fail_reason`, `print_error`, `mc_print_error_code`** — детальніша діагностика причини провалу друку.
8. **`upload.status`/`upload.progress`** — прогрес-бар при відправці файлу на друк через WebApp.


тут є все що потрібно парсити