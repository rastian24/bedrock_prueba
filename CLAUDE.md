# Bedrock — Prompt para Claude Code

## Descripción General

Creá una aplicación de escritorio llamada **Bedrock**, un editor de notas tipo Obsidian construido en Python. La app permite gestionar un "vault" (carpeta local) de archivos Markdown (.md), con enlaces bidireccionales entre notas, editor WYSIWYG, sistema de tags, búsqueda full-text y panel de backlinks.

---

## Stack Tecnológico

- **Python 3.11+**
- **PySide6** — Framework de UI (licencia LGPL)
- **QTextEdit con QSyntaxHighlighter personalizado** — Editor WYSIWYG de Markdown
- **mistune** — Parser de Markdown a HTML
- **QWebEngineView** — Renderizado de preview HTML (integrado en el editor WYSIWYG)
- **whoosh** — Motor de búsqueda full-text indexada
- **pathlib** — Manejo del sistema de archivos
- **re (stdlib)** — Extracción de wikilinks y tags con regex
- **json (stdlib)** — Persistencia de configuración (último vault, preferencias)

### Gestión de dependencias

Usá **uv** como gestor de paquetes. Generá un `pyproject.toml` con todas las dependencias del proyecto.

---

## Arquitectura del Proyecto

```
bedrock/
├── pyproject.toml
├── README.md
├── main.py                     # Entry point
├── core/
│   ├── __init__.py
│   ├── vault.py                # Gestión del vault (leer/escribir/listar archivos .md)
│   ├── markdown_parser.py      # Parsing de Markdown + extracción de [[wikilinks]] y #tags
│   ├── search_engine.py        # Índice de búsqueda full-text con Whoosh
│   ├── backlinks.py            # Motor de backlinks (qué notas enlazan a cuál)
│   └── config.py               # Configuración persistente (último vault, preferencias)
├── ui/
│   ├── __init__.py
│   ├── main_window.py          # Ventana principal con layout de paneles
│   ├── vault_selector.py       # Diálogo de selección/creación de vault al iniciar
│   ├── editor/
│   │   ├── __init__.py
│   │   ├── wysiwyg_editor.py   # Editor WYSIWYG principal
│   │   ├── markdown_highlighter.py  # Syntax highlighter para Markdown
│   │   └── wikilink_handler.py # Detección y navegación de [[wikilinks]]
│   ├── file_tree.py            # Explorador de archivos (sidebar izquierdo)
│   ├── backlinks_panel.py      # Panel de backlinks (sidebar derecho)
│   ├── search_panel.py         # Panel de búsqueda
│   └── tag_panel.py            # Panel de tags
└── resources/
    ├── dark_theme.qss          # Stylesheet tema oscuro tipo Obsidian
    └── icons/                  # Íconos de la app (usar iconos de sistema o lucide)
```

---

## Funcionalidades — Especificación Detallada

### 1. Selector de Vault (al iniciar)

- Al abrir la app por primera vez, mostrar un diálogo que permita:
  - **Abrir vault existente**: seleccionar una carpeta del sistema de archivos
  - **Crear nuevo vault**: elegir ubicación y nombre para una nueva carpeta
- Guardar el último vault abierto en un archivo de configuración (`~/.config/bedrock/config.json`) y reabrirlo automáticamente en futuros inicios
- Incluir un menú o botón para cambiar de vault sin cerrar la app

### 2. Explorador de Archivos (sidebar izquierdo)

- Mostrar el árbol de carpetas y archivos `.md` del vault usando un `QTreeView` con `QFileSystemModel` filtrado
- Operaciones disponibles vía menú contextual (click derecho):
  - Crear nueva nota (.md)
  - Crear nueva carpeta
  - Renombrar archivo/carpeta
  - Eliminar archivo/carpeta (con confirmación)
  - Mover archivo/carpeta (drag & drop)
- Al hacer click en un archivo, abrirlo en el editor
- Resaltar visualmente el archivo actualmente abierto
- Icono diferenciado para carpetas y archivos

### 3. Editor WYSIWYG de Markdown

Este es el componente central. Implementar un editor que muestre el Markdown con formato visual en tiempo real mientras el usuario escribe.

#### Comportamiento WYSIWYG

- Usar un `QTextEdit` con un `QSyntaxHighlighter` personalizado que aplique formato visual al Markdown en tiempo real:
  - `# Encabezado 1` → se muestra con fuente grande y bold
  - `## Encabezado 2` → fuente mediana y bold
  - `**negrita**` → se muestra en negrita (ocultar los `**` o mostrarlos en gris)
  - `*cursiva*` → se muestra en cursiva
  - `` `código` `` → se muestra con fuente monoespaciada y fondo ligeramente diferente
  - `- item` y `1. item` → indentación visual de lista
  - `> cita` → indentación y barra lateral visual
  - `---` → línea horizontal visual
  - `[[wikilink]]` → se muestra como enlace clickeable (color diferenciado, cursor pointer)
  - `#tag` → se muestra con color diferenciado (como badge o texto coloreado)
  - Links markdown `[texto](url)` → se muestra como enlace clickeable
- El archivo subyacente siempre se guarda como Markdown puro (texto plano .md)
- Guardado automático al dejar de escribir por 2 segundos (debounce) o al cambiar de nota
- Mostrar en la barra de estado: nombre del archivo, conteo de palabras, y estado de guardado

#### Atajos de teclado

| Atajo | Acción |
|-------|--------|
| `Ctrl+B` | Alternar negrita (**texto**) |
| `Ctrl+I` | Alternar cursiva (*texto*) |
| `Ctrl+K` | Insertar link `[](url)` |
| `Ctrl+Shift+K` | Insertar wikilink `[[]]` |
| `Ctrl+S` | Guardar nota |
| `Ctrl+N` | Nueva nota |
| `Ctrl+P` | Búsqueda rápida de notas (Quick Open tipo Ctrl+P de VS Code) |
| `Ctrl+Shift+F` | Búsqueda en todo el vault |
| `Ctrl+L` | Insertar lista no ordenada |
| `Ctrl+Shift+L` | Insertar lista ordenada |
| `Ctrl+Shift+C` | Insertar bloque de código |
| `Ctrl+H` | Insertar encabezado (ciclar H1 → H2 → H3 → texto normal) |

### 4. Sistema de Wikilinks `[[enlaces]]`

- **Detección**: Parsear el contenido buscando el patrón `[[nombre de nota]]`
- **Navegación**: Al hacer click en un wikilink:
  - Si la nota existe → abrirla en el editor
  - Si la nota NO existe → crearla automáticamente y abrirla
- **Autocompletado**: Al escribir `[[`, mostrar un popup/dropdown con las notas existentes filtradas por lo que el usuario va escribiendo
- **Soporte para alias**: `[[nombre de nota|texto visible]]` — el link muestra "texto visible" pero enlaza a "nombre de nota"
- Los wikilinks son case-insensitive para la búsqueda de archivos

### 5. Sistema de Backlinks

- Panel lateral (sidebar derecho, colapsable) que muestre para la nota actualmente abierta:
  - **Backlinks directos**: lista de todas las notas que contienen un `[[enlace]]` a esta nota
  - Para cada backlink, mostrar un preview del contexto (la línea donde aparece el enlace)
- Al hacer click en un backlink, navegar a esa nota
- El índice de backlinks se construye al abrir el vault y se actualiza incrementalmente al guardar una nota

### 6. Sistema de Tags `#etiquetas`

- **Detección**: Parsear el contenido buscando `#tag` (alfanumérico, puede incluir guiones y barras: `#proyecto/subtema`)
- **Panel de tags** (en sidebar izquierdo, debajo del explorador de archivos o como tab):
  - Lista de todos los tags usados en el vault con conteo de ocurrencias
  - Al hacer click en un tag, mostrar todas las notas que lo contienen
- **Tags jerárquicos**: soportar `#parent/child` como tags anidados
- Los tags se muestran con color diferenciado en el editor

### 7. Búsqueda Full-Text

- **Motor**: Whoosh con índice almacenado en la carpeta del vault (`.bedrock/index/`)
- **Búsqueda rápida** (`Ctrl+P`): popup centrado tipo "Quick Open" que busca por nombre de archivo. Resultados en tiempo real mientras se escribe.
- **Búsqueda en vault** (`Ctrl+Shift+F`): panel dedicado que busca en el contenido de todas las notas. Mostrar:
  - Nombre de la nota
  - Preview del contexto donde aparece el término (con highlight del match)
  - Conteo de ocurrencias por nota
- El índice se construye al abrir el vault y se actualiza incrementalmente al guardar una nota
- Soportar operadores básicos: AND, OR, frases exactas con comillas

---

## Diseño Visual — Tema Oscuro

Implementar un tema oscuro inspirado en Obsidian usando un archivo QSS (`dark_theme.qss`).

### Paleta de colores

| Elemento | Color |
|----------|-------|
| Fondo principal | `#1e1e1e` |
| Fondo sidebar | `#252525` |
| Fondo editor | `#1e1e1e` |
| Texto principal | `#dcddde` |
| Texto secundario | `#999999` |
| Acento / links | `#7f6df2` (violeta tipo Obsidian) |
| Wikilinks | `#7f6df2` |
| Tags | `#e5c07b` (amarillo dorado) |
| Bordes | `#333333` |
| Selección | `#264f78` |
| Hover en sidebar | `#2a2a2a` |
| Barra de título | `#191919` |
| Botones | `#3a3a3a` fondo, `#dcddde` texto |

### Tipografía

- **Editor**: Fuente monoespaciada para el markdown source, "Inter" o "Segoe UI" para el contenido WYSIWYG renderizado
- **Sidebar**: Sans-serif, tamaño 13px
- **Encabezados en editor**: H1 = 28px, H2 = 22px, H3 = 18px, texto normal = 16px

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  Bedrock — nombre_del_vault              [─] [□] [✕]    │
├──────────┬────────────────────────┬─────────────────────┤
│          │                        │                     │
│ Explorador│      Editor WYSIWYG   │   Panel Backlinks   │
│ de        │                        │                     │
│ Archivos  │                        │   ─────────────     │
│           │                        │   Nota A            │
│ ────────  │                        │     "...contexto.." │
│ Tags      │                        │   Nota B            │
│  #tag1 (5)│                        │     "...contexto.." │
│  #tag2 (3)│                        │                     │
│           │                        │                     │
├──────────┴────────────────────────┴─────────────────────┤
│ archivo.md | 245 palabras | Guardado ✓                   │
└─────────────────────────────────────────────────────────┘
```

- Sidebar izquierdo: ancho fijo 250px, colapsable con `Ctrl+\`
- Sidebar derecho (backlinks): ancho fijo 280px, colapsable
- Editor: ocupa todo el espacio restante
- Barra de estado inferior: nombre del archivo, conteo de palabras, estado de guardado

---

## Comportamiento de la Aplicación

### Al iniciar
1. Leer configuración de `~/.config/bedrock/config.json`
2. Si hay vault guardado y existe → abrirlo directamente
3. Si no → mostrar diálogo de selección de vault
4. Al abrir vault: indexar notas (backlinks + búsqueda full-text) en background

### Al crear nueva nota
1. Mostrar diálogo con campo de nombre
2. Crear archivo `nombre.md` en la carpeta actual del explorador
3. Abrirla en el editor con foco automático

### Al guardar nota
1. Escribir el contenido Markdown al archivo
2. Actualizar índice de backlinks incrementalmente
3. Actualizar índice de búsqueda incrementalmente
4. Actualizar panel de tags

### Al eliminar nota
1. Confirmar con diálogo
2. Eliminar archivo
3. Actualizar índices
4. Si estaba abierta, cerrar el editor o mostrar nota vacía

---

## Requisitos Técnicos

- Toda la app debe correr en un solo proceso con UI responsiva (usar `QThread` o `QRunnable` para indexación en background)
- El vault puede tener cientos o miles de notas — la búsqueda y el indexado deben ser eficientes
- No usar base de datos SQL — los archivos .md son la fuente de verdad
- La carpeta `.bedrock/` dentro del vault almacena datos internos (índice de búsqueda, caché de backlinks)
- El código debe estar bien organizado, con type hints de Python, y docstrings en las clases/métodos principales
- Manejar errores de forma elegante (archivos bloqueados, permisos, vault corrupto, etc.)

---

## Orden de Implementación Sugerido

Implementá las funcionalidades en este orden, asegurándote de que cada paso funcione antes de avanzar al siguiente:

1. **Setup del proyecto**: `pyproject.toml`, estructura de carpetas, entry point
2. **Ventana principal + tema oscuro**: Layout vacío con sidebars y editor placeholder, aplicar QSS
3. **Selector de vault**: Diálogo de apertura/creación de vault con persistencia de config
4. **Explorador de archivos**: QTreeView con QFileSystemModel filtrado para .md
5. **Editor WYSIWYG**: QTextEdit con syntax highlighter que renderice Markdown visualmente
6. **Guardado automático**: Debounce de 2 segundos + Ctrl+S
7. **Wikilinks**: Detección, resaltado, navegación, autocompletado, creación de notas nuevas
8. **Backlinks**: Indexado del vault + panel de backlinks
9. **Tags**: Detección, panel de tags, navegación
10. **Búsqueda full-text**: Whoosh indexing + Quick Open (Ctrl+P) + búsqueda en vault (Ctrl+Shift+F)
11. **Atajos de teclado**: Todos los atajos documentados
12. **Pulido**: Barra de estado, manejo de errores, edge cases
