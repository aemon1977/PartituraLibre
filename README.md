# Partitura Libre

Aplicación de escritorio gratuita para **Windows 11** y **Debian 13** (preparada para Ubuntu 24.04) con dos funciones:

- **Partituras:** graba o importa una melodía, detecta las notas y crea MIDI y MusicXML editables.
- **Letras:** pasa voz (hablada o cantada) a texto editable, con marcas de tiempo.

Todo se procesa en tu equipo: sin cuentas, sin nube, sin cuotas de minutos ni de exportaciones.

![Partituras](docs/vista-previa-partituras.png)
![Letras](docs/vista-previa-letras.png)

## Es portable: una carpeta y nada más

Todo lo que el programa instala o descarga queda **dentro de su carpeta** (`runtime/`, `models/`, `data/`, `config/`, `logs/`, `temp/`). No pide contraseña de administrador y no toca el sistema, el registro ni tu perfil. **Para desinstalarlo, borra la carpeta** (o usa *Ajustes → Desinstalar*).

Lo único que no se borra con ella son las copias que tú exportes a otros sitios; el programa te avisa cada vez.

## Instalación

Necesitas conexión a Internet solo la primera vez y unos **1,6 GB libres** (más los modelos de voz que elijas).

### Debian 13 / Ubuntu 24.04 (64 bits)

```sh
tar -xzf PartituraLibre-1.1.0-linux-x64.tar.gz
cd PartituraLibre
./iniciar-linux.sh
```

### Windows 11 (64 bits)

1. Descomprime `PartituraLibre-1.1.0-windows11-x64.zip` en una carpeta tuya (por ejemplo, Documentos).
2. Doble clic en `iniciar-windows.bat`.

### Qué pasa en el primer arranque

El lanzador muestra lo que va a bajar y lo guarda en `runtime/`:

| Componente | Tamaño en disco |
|---|---|
| Gestor `uv` | ≈ 50 MB |
| Python 3.11 portable | ≈ 90 MB |
| Paquetes «app» (interfaz Qt, audio, voz a texto) | ≈ 650 MB (≈ 460 MB en Windows) |
| Paquetes «partituras» (Basic Pitch, music21) | ≈ 710 MB (≈ 550 MB en Windows) |

Después comprueba que todo se puede importar y abre la ventana. Los siguientes arranques son inmediatos y no usan Internet.

Opcionales, solo cuando pulsas el botón correspondiente:

| Descarga | Tamaño | Dónde |
|---|---|---|
| Modelo de voz `tiny` / `base` / `small` / `medium` / `large-v3` | 75 / 145 / 485 / 1530 / 3090 MB | `models/whisper/` |
| MuseScore Studio 4.7.5 portable (opcional; la app edita y exporta PDF sin él) | 195 MB (≈ 570 MB descomprimido) | `runtime/musescore/` |

## Uso

### Partituras

La sección está organizada como un editor de partituras:

- **Arriba, dos barras.** La de archivo: *Nueva*, *Abrir…*, *Guardar versión*, deshacer y rehacer, *▶ Oír*, *PDF…*, *MIDI…*, *MusicXML…*, *Carpeta* y los botones que muestran u ocultan los paneles laterales. La de notas: *✎ Introducir*, las cinco figuras (redonda a semicorchea), semitono y octava arriba o abajo, mover la nota antes o después, *+ Nota*, *Borrar*, la letra de la nota elegida, la clave, los nombres Do-Re-Mi y el zoom.
- **En el centro, la partitura** en una hoja: título, clave, compás de 4/4, barras y números de compás, figuras, silencios, nombres de nota y letra, repartida en sistemas según el ancho de la ventana.
- **A la izquierda, el panel *Grabación*** (grabar o importar, y convertir en partitura). **A la derecha, la *Lista de notas*** con los valores exactos.

**Todo se hace dentro de la app; no hace falta MuseScore** para editar, oír ni sacar el PDF.

Tres maneras de empezar:

- **Desde un audio.** Elige la entrada de audio, *Probar nivel* y *Grabar* (con *Ver las notas mientras grabo* la partitura se dibuja en vivo como borrador), o importa un WAV, MP3, FLAC u OGG. Después, *Detectar notas y crear partitura*. Si marcas *Añadir la letra bajo las notas*, se reconoce la voz y cada palabra va bajo su nota (hace falta un modelo de voz descargado).
- **Desde una partitura existente.** *Abrir…* convierte un MusicXML, MXL o MIDI en una partitura editable; el archivo original se guarda en el proyecto.
- **En blanco.** *Nueva* crea una hoja vacía con el modo *Introducir* activado.

Editar:

| Quiero… | Cómo |
|---|---|
| Elegir una nota | Clic sobre ella; **← →** pasan a la anterior o la siguiente |
| Cambiar su altura | Arrastrarla arriba o abajo, **↑ ↓** (con **Ctrl**, una octava) o los botones ♯ ♭ 8ª |
| Cambiar su duración | Pulsar una figura |
| Moverla en el tiempo | **Mayús + ← →** o los botones ◀ ▶ (de semicorchea en semicorchea) |
| Escribir notas nuevas | Activar *✎ Introducir*, elegir figura y hacer clic en el pentagrama a la altura deseada; o **N** para añadir tras la nota elegida |
| Borrar | **Supr** |
| Poner o corregir la letra | Campo *Letra de la nota* |
| Deshacer o rehacer | **Ctrl+Z**, **Ctrl+Y** |
| Oír el resultado | **Espacio** o *▶ Oír* (suena desde la nota elegida, con un timbre sencillo) |
| Ajustar al segundo | Panel *Lista de notas* |

Guardar y exportar: *Guardar versión* crea MIDI y MusicXML nuevos con tus cambios, sin pisar los anteriores. *PDF…* escribe en A4 la partitura tal como la ves, con clave, nombres y letra. MuseScore es opcional: si lo tienes, aparece un botón para abrir en él el MusicXML guardado.

> La hoja de la app coloca cada nota a su altura exacta, elige la figura más parecida a su duración y marca compases y silencios según el tempo. No dibuja puntillos, ligaduras, tresillos ni armaduras, y las alteraciones se escriben siempre con sostenidos. El MusicXML se cuantiza a semicorcheas.
>
> La detección desde audio es automática y aproximada. Va bien con una melodía o un instrumento solo. Con varios instrumentos, acordes densos o batería habrá notas falsas o ausentes: revisa siempre el resultado.

### Letras

1. **Elige un modelo** y pulsa *Descargar modelo* (una sola vez). `small` es el recomendado para español; `tiny` y `base` son más rápidos y fallan más; `medium` y `large-v3` son más precisos y lentos.
2. **Elige la entrada de audio.** Además de los micrófonos, en Linux aparecen entradas **«Sonido del equipo · …»**, que graban directamente lo que suena por una salida (Spotify, un vídeo, una videollamada). Para transcribir algo que suena en el ordenador usa siempre esa opción —la marcada «salida en uso»— y no el micrófono: por los altavoces llega flojo y con ruido, y el reconocimiento sale vacío.
3. **Graba, dicta o importa** audio o vídeo (WAV, MP3, FLAC, OGG, M4A, MP4, MKV…). Con *Transcribir mientras hablo* aparece un borrador cada pocos segundos; al detener, la toma completa se transcribe de nuevo con más precisión.
4. **Idioma:** español, detección automática u otro de la lista.
5. **Voz hablada o voz cantada (modo de prueba).** Con canto, la música y los coros confunden al modelo: los versos poco fiables se marcan con **⚠** para que los escuches y corrijas. El programa no inventa texto donde no entiende.
6. **Revisa y exporta.** El texto es editable (una línea por frase, marcas `[mm:ss.cc]` opcionales), se puede buscar y copiar, y se exporta a **TXT, SRT, VTT o LRC**.

### Grabaciones / Proyectos

Historial de todas las tomas con su audio y sus resultados. Desde aquí puedes reabrirlas, ver su carpeta, exportar una copia o eliminarlas.

### Ajustes

Modelos de voz, MuseScore portable, **Diagnóstico** (runtime, micrófonos, motores, modelos, editor, espacio libre; guarda un informe en `logs/` sin grabaciones ni datos personales), tamaño de cada carpeta, vaciado de temporales y **desinstalación**.

## Formatos de salida

| Sección | Archivos |
|---|---|
| Partituras | `.wav` (toma original), `.mid`, `.musicxml`, `.notas.json` (notas editables), `.pdf` |
| Letras | `.wav` u original importado, `.txt`, `.letra.json` (frases con tiempos), `.srt`, `.vtt`, `.lrc` |

Cada proyecto es una carpeta en `data/proyectos/` (o donde tú elijas).

## Solución de problemas

| Síntoma | Qué hacer |
|---|---|
| El lanzador dice que un conjunto de paquetes no funciona | `./iniciar-linux.sh --reparar` o `iniciar-windows.bat --reparar`. Reinstala dentro de la carpeta, nada global. |
| Quiero ver qué falla sin abrir la ventana | `./iniciar-linux.sh --diagnostico` (o `iniciar-windows.bat --diagnostico`). |
| «No se pudo cargar PortAudio» (Linux) | Falta la biblioteca de audio del sistema `libportaudio2`. El programa no instala nada en el sistema: pídeselo a quien administre el equipo. Mientras tanto puedes importar archivos. |
| La ventana no se abre en una sesión X11 (Linux) | Qt necesita `libxcb-cursor0` del sistema. En sesiones Wayland (las de Debian 13 y Ubuntu 24.04 por defecto) no hace falta. |
| «No se pudo abrir el micrófono» | Otro programa lo está usando o no hay permiso. Pulsa *Actualizar* y elige otro. En Windows: Configuración → Privacidad y seguridad → Micrófono. |
| No aparece mi micrófono | Conéctalo y pulsa *Actualizar*. En Linux se listan los que publica PipeWire/PulseAudio; si no hay servidor de sonido se muestran los dispositivos ALSA. |
| La transcripción sale vacía | El motor no encontró voz inteligible y no inventa texto. Si era música del propio equipo, grábala con «Sonido del equipo»; si es una canción, marca «Voz cantada»; revisa el idioma y prueba el modelo `medium`. |
| «Nivel de grabación muy bajo» | Acerca el micrófono o sube la entrada en el control de sonido del sistema. |
| «La toma está en silencio» | El micrófono está silenciado, apagado o no es la entrada elegida. Usa *Probar nivel*. |
| «Grabación incompleta» | El equipo iba muy cargado o el disco se llenó. La toma se conserva; el aviso dice cuánto falta. |
| La transcripción se cierra sola | Falta memoria: usa un modelo más pequeño. Detalle en `logs/motores.log`. |
| No suena *▶ Oír* | Usa la salida de audio predeterminada del sistema: compruébala en el control de sonido. |
| MuseScore no arranca (Linux) | Es opcional. La copia portable necesita X11 o XWayland (lo normal en escritorios actuales). |
| El programa se cerró mientras grababa | Al volver a abrirlo, la toma aparece como «Interrumpida» con el audio hasta el corte. |

## Versión anterior

La interfaz clásica (1.0, con tarjetas en dos columnas) se conserva en la etiqueta `v1.0-clasica` del repositorio y, en el equipo de desarrollo, como copia ejecutable en la carpeta hermana `PartituraLibre-v1-clasica`.

## Para desarrollo

```sh
./herramientas/probar.sh            # todas las pruebas, con el runtime portable
./herramientas/bloquear.sh          # regenera app/requisitos/*.txt (bloqueos con hashes)
python3 herramientas/empaquetar.py  # crea dist/ con los tres paquetes
```

Arquitectura y decisiones: [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) · Licencias: [docs/LICENCIAS.md](docs/LICENCIAS.md) · Qué se ha probado de verdad: [docs/INFORME-PRUEBAS.md](docs/INFORME-PRUEBAS.md)
