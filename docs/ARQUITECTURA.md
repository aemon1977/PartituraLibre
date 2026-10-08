# Arquitectura y decisiones

Proyecto nuevo, sin código heredado. Este documento recoge lo que se decidió y por qué.

## Estructura

```text
PartituraLibre/
  iniciar-linux.sh / iniciar-windows.bat   lanzadores (lo único que depende del sistema operativo)
  app/
    partitura_libre/
      lanzar.py        prepara y verifica los paquetes; abre la app (solo stdlib)
      rutas.py         todas las rutas salen de la carpeta del programa; entorno de los procesos hijo
      config.py        preferencias (config/ajustes.json)
      audio.py         captura: micrófonos, grabadora por bloques, escritor WAV
      proyectos.py     biblioteca: una carpeta por toma con su audio y sus resultados
      partituras.py    utilidades de notas (integración de trozos, filtro de armónicos)
      letras.py        modelos de voz, texto editable por segmentos
      exportar.py      TXT / SRT / VTT / LRC y su lectura
      editor.py        MuseScore portable o existente; PDF
      descargas.py     descargas con progreso, cancelación y sha256
      tareas.py        procesos de análisis en segundo plano, cancelables
      diagnostico.py   comprobaciones e informe
      limpieza.py      contenido de la carpeta y desinstalación
      workers/notas.py audio -> notas -> MIDI -> MusicXML   (conjunto «partituras»)
      workers/voz.py   voz -> texto                         (conjunto «app»)
      ui/              interfaz Qt: tema, captura, partituras, letras, proyectos, ajustes, ventana
    requisitos/        *.in (lo pedido), *.txt (bloqueo con hashes para Linux y Windows), exclusiones.txt
  runtime/   uv, Python 3.11, site-app/, site-partituras/, musescore/     (descargado)
  models/    modelos de voz                                               (descargado a petición)
  data/      proyectos; datos de MuseScore portable
  config/  logs/  temp/
  tests/  herramientas/  docs/
```

## Decisiones

**1. Un solo intérprete, el del paquete, para todo.** El prototipo anterior abría la ventana con un Python y tenía `sounddevice`/`soundfile` en otro. Aquí no existe esa posibilidad:

- el lanzador solo ejecuta `runtime/python/…/python`;
- `lanzar.py` se niega a seguir si `sys.executable` no está dentro de `runtime/`;
- antes de abrir la ventana **importa de verdad** cada dependencia con ese intérprete y esas rutas; si algo falla lo nombra y propone `--reparar`, que reinstala dentro de la carpeta;
- la app y los motores se lanzan con `sys.executable`, nunca con un `python` del PATH.

Lo cubre `tests/test_dependencias.py`, incluido el caso de dependencia ausente y el de arrancar con el Python del sistema.

**2. Python 3.11 para todo, con dos conjuntos de paquetes aislados.** Debian 13 trae Python 3.13 y Basic Pitch 0.4.0 solo declara soporte hasta 3.11. En lugar de dos intérpretes se descarga uno (3.11, de python-build-standalone mediante `uv`) y dos carpetas de paquetes: `site-app` (interfaz, audio, voz) y `site-partituras` (Basic Pitch, music21). Basic Pitch corre siempre en un proceso aparte con su propia carpeta. El Python del sistema no se usa ni se modifica.

**3. Carpetas de paquetes en vez de entornos virtuales.** Un venv guarda rutas absolutas y se rompe al mover la carpeta. `uv pip install --target` deja paquetes sin rutas fijas y el intérprete de python-build-standalone es reubicable: la carpeta se puede mover (probado).

**4. `uv` confinado.** Vive en `runtime/uv`, con `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR` y `UV_NO_CONFIG` apuntando dentro; `python install --no-bin --no-registry` evita los enlaces en `~/.local/bin` y el registro de Windows. La caché de descarga se borra al terminar. Versión y sha256 fijados en los lanzadores.

**5. Interfaz con Qt (PySide6), no Tkinter.** Se probó primero Tkinter: el Tk de python-build-standalone no incluye Xft, así que en Linux solo ofrece fuentes de mapa de bits sin suavizado. No se puede empaquetar limpiamente sin instalar `python3-tk`, por lo que se eligió PySide6-Essentials, que va entero en un wheel. Requisitos del sistema en Linux: en sesiones X11, `libxcb-cursor0`; en Wayland, ninguno adicional.

**6. Basic Pitch con ONNX, sin TensorFlow.** El paquete trae su modelo también en ONNX. Se excluye TensorFlow (`exclusiones.txt`): 1,5 GB menos y los mismos wheels en Linux y Windows.

**7. Captura que no pierde audio en silencio.** Callback mínimo → cola acotada → hilo escritor. Si la cola se llena o PortAudio avisa de desbordamiento, se cuenta y la toma queda marcada como incompleta con el motivo. El WAV se escribe con un escritor propio que **corrige la cabecera cada segundo**: tras un cierre brusco el archivo es válido hasta ese punto y el proyecto aparece como «interrumpido». No hay límite de duración; el único tope es el del formato WAV (4 GB ≈ 13 h en mono), que se avisa y cierra bien la toma.

**8. Audio largo por trozos con solape.** `workers/notas.py` lee 120 s cada vez (nunca el archivo entero) con 2 s de contexto a cada lado. Solo cuentan las notas que empiezan dentro del trozo; una nota que sigue sonando en el siguiente se alarga en vez de partirse (`partituras.integrar`). Se descartan notas «fantasma» que son armónicos débiles de otra simultánea (`quitar_armonicos`).

**9. Análisis en procesos aparte.** Interfaz siempre libre; cancelar es terminar el proceso. Los resultados se escriben como `.parcial` y solo se renombran al acabar; al cancelar se borran. El motor de voz es un proceso persistente (carga el modelo una vez) que recibe órdenes por la entrada estándar.

**10. Voz a texto con faster-whisper en CPU (int8).** Sin GPU ni claves. Los modelos se bajan a `models/whisper/` solo al pulsar el botón, con tamaño, memoria y progreso; se verifica el sha256 que publica el repositorio. `HF_HUB_OFFLINE=1` impide que ninguna biblioteca descargue por su cuenta. Voz cantada: sin filtro de silencios ni arrastre de contexto y umbral de duda más estricto. **No se incluye separación de voz e instrumentos**: las herramientas libres disponibles (Demucs) exigen PyTorch (≈ 2 GB) y no se ha verificado que compense.

**11. Edición de partituras en dos niveles.** En la app: tabla y rollo de piano para corregir notas y regenerar MIDI/MusicXML. Edición gráfica y PDF: MuseScore Studio, descargado a `runtime/musescore/` (AppImage extraído en Linux, PortableApps en Windows) o uno ya instalado, que se usa sin modificarlo. A la copia portable se le fijan `HOME` y `XDG_*` dentro de la carpeta, porque de otro modo crea `~/Documents/MuseScore4`.

**12. PortAudio en Linux es el del sistema.** El wheel de `sounddevice` solo lo incluye en Windows. No hay forma limpia de distribuirlo sin instalar nada, así que se usa `libportaudio2` si existe y, si no, el diagnóstico lo explica y la importación de archivos sigue funcionando.

**13. Nada en el perfil.** Cachés y temporales (`XDG_CACHE_HOME`, `TMPDIR`, `NUMBA_CACHE_DIR`, `MPLCONFIGDIR`, `HF_HOME`) apuntan a la carpeta. Los motores, que no usan audio, reciben además `XDG_CONFIG_HOME`/`XDG_DATA_HOME` propios. Si no existe la cookie de PulseAudio del usuario, se indica una dentro de `config/` para que la biblioteca del sistema no la cree en el perfil.

## Funciones y criterio de aceptación

| Función | Se acepta cuando | Evidencia |
|---|---|---|
| Arranque portable | Instala en carpeta nueva con espacios y tildes, sin escribir fuera; funciona tras moverla y sin red | Informe, apartados 2–4 |
| Dependencias coherentes | Un módulo ausente se detecta antes de la ventana y se nombra | `test_dependencias` |
| Grabación | Señal conocida se guarda idéntica; pausa, cancelación, disco lleno y desbordes se notifican | `test_audio` |
| Sesión larga | 40 min sin pérdidas por la misma vía que una toma real | `test_audio` |
| Audio → MIDI → MusicXML | Una escala conocida produce exactamente esas notas | `test_partitura_flujo` |
| Corrección de notas | Editar crea una versión nueva y no altera la anterior | `test_partitura_flujo`, `test_ui` |
| Voz → texto | Idioma detectado, tiempos crecientes, exportación y reimportación | `test_letras_flujo` |
| Exportación de letras | TXT/SRT/VTT/LRC exactos y de ida y vuelta | `test_exportar` |
| Proyectos | Nombres únicos, audio asociado a resultados, tomas interrumpidas marcadas | `test_rutas_proyectos` |
| Interfaz | Botones bloqueados según el estado; errores explicados; cancelación limpia | `test_ui` |
| PDF | MuseScore portable convierte MusicXML y MIDI sin escribir fuera | Informe, apartado 6 |
| Desinstalación | Borra la carpeta y solo la carpeta | `test_limpieza`, informe apartado 4 |
