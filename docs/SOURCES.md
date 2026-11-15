# Источники телеметрии Boshy

[memory.py](../boshy_env/memory.py) — собственный читатель памяти на Python.
Он читает память нативного процесса Windows через `ReadProcessMemory` по адресам,
опубликованным авторами инструментов для спидранов и TAS. Эти инструменты
помогают измерять прохождение: autosplitter LiveSplit узнаёт смену комнаты
по памяти, а исследования boshyst раскрывают расположение объектов движка.
Мы используем эти сведения для наблюдений и определения конца эпизода.

| Источник | Использовано |
| --- | --- |
| [AnsoWizard/AutoSplitters, IWBTB.asl](https://github.com/AnsoWizard/AutoSplitters/blob/16cd0c731bb94d25d39e41446b2e6f1ae21e9ae0/IWBTB.asl) | Цепочка указателей на комнату; туториал `36`. |
| [AnsoWizard/AutoSplitters, Boshy.asl](https://github.com/AnsoWizard/AutoSplitters/blob/16cd0c731bb94d25d39e41446b2e6f1ae21e9ae0/Boshy.asl) | Выход из туториала в комнату `3`. |
| [Pixelsuft/boshyst, utils.cpp](https://github.com/Pixelsuft/boshyst/blob/55e40b3e5a232a040e56aa2a249a501ca456352e/src/utils.cpp#L343) | Handle игрока `16` в туториале и правило определения смерти. |
| [Pixelsuft/boshyst, ghidra_headers.h](https://github.com/Pixelsuft/boshyst/blob/55e40b3e5a232a040e56aa2a249a501ca456352e/src/ghidra_headers.h#L1523) | Смещения координат, списка объектов и счётчика кадров Clickteam runtime. |
| [Pixelsuft/boshyst, conf.cpp](https://github.com/Pixelsuft/boshyst/blob/55e40b3e5a232a040e56aa2a249a501ca456352e/src/conf.cpp#L184) | Подтверждение механики курсора, который движется к игроку. Настройка мода `no_mouse_move` здесь не применяется. |
| [shar, описание собственного TAS](https://tasvideos.org/6843S) | Фронты клавиш, одновременные Left+Right, выстрелы в checkpoints и телепорты в туториале. |

Спасибо Pixelsuft и авторам boshyst за исследование движка, AnsoWizard — за autosplitter.
Лицензия boshyst — [DBAD Public License 1.2](https://github.com/Pixelsuft/boshyst/blob/55e40b3e5a232a040e56aa2a249a501ca456352e/LICENSE.md).
Исходники и DLL этих проектов здесь не распространяются; используются сведения об адресах.

## Карта указателей

Указатели игры — little-endian 32 bit; `base` — базовый адрес EXE,
полученный через Windows Toolhelp32 API.
`ptr` читает указатель, `i32` — знаковое целое.

```text
room    = i32(ptr(ptr(base + 0x59A94) + 0x268) + 0xA8)
run     = ptr(base + 0x59A9C)
frame   = i32(run + 0xD0)
objects = ptr(run + 0x1278)
player  = ptr(objects + 16 * 8)                 # только room == 36
x       = i32(player + 0x4C)
y       = i32(player + 0x54)
dead    = player == 0 or x > 60000 or y == 0
```

В boshyst туториал имеет runtime scene `35`, в LiveSplit — room `36`:
это разные способы нумерации одной сцены. Handle игрока в ней — `16`.
Вне туториала координаты не читаются, а `dead=False` означает, что детектор не применяется.
Нулевой указатель самого игрока означает смерть; ошибка чтения памяти вызывает исключение.

Адреса рассчитаны на локальную 32-битную сборку `I Wanna Be The Boshy.exe`.
Для другой сборки смещения могут отличаться. Результаты проверки на настоящей
игре приведены в [README.md](../README.md).

Windows API: [ReadProcessMemory](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-readprocessmemory),
[снимок модулей процесса](https://learn.microsoft.com/en-us/windows/win32/toolhelp/traversing-the-module-list),
[SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput).
